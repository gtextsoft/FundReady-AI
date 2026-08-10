import { create } from 'zustand';
import { api, isUnavailable, type SaveResult } from '@/api';
import type { UnmappedAnswer } from '@/api/profile-mapping';
import { isAuditFinished, type AuditReport, type AuditRun } from '@/domain/audit';
import { assess } from '@/domain/scoring';
import { EMPTY_PROFILE, type Assessment, type FounderProfile } from '@/domain/types';

/**
 * How often to ask whether the audit has finished, and when to give up.
 *
 * The audit runs an Opus-tier model over a 16k budget, so seconds-to-minutes
 * is normal and a tight poll would just bill the server for nothing. Giving up
 * stops the *polling*, not the audit — the run continues, and `resumeAudit`
 * picks it up next time the screen opens.
 */
const POLL_INTERVAL_MS = 3_000;
const POLL_TIMEOUT_MS = 5 * 60_000;

/**
 * Pause after the last keystroke before writing the profile. Short enough that
 * a founder who leaves mid-step does not lose work; long enough that typing a
 * sentence is one PATCH, not one per character.
 */
const AUTOSAVE_MS = 900;

const wait = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

export type Step = 1 | 2 | 3 | 4 | 5;

/**
 * Bumped on every local edit. A save that started against an older revision
 * must not clear `dirty` or replace the form with a stale server read-back.
 */
let editRevision = 0;
let autosaveTimer: ReturnType<typeof setTimeout> | null = null;
/** Serialises overlapping save() calls so Continue + debounce cannot race. */
let saveChain: Promise<unknown> = Promise.resolve();

function clearAutosaveTimer() {
  if (autosaveTimer) {
    clearTimeout(autosaveTimer);
    autosaveTimer = null;
  }
}

function scheduleAutosave(save: () => Promise<SaveResult>) {
  clearAutosaveTimer();
  autosaveTimer = setTimeout(() => {
    autosaveTimer = null;
    // Best-effort: a failed autosave leaves `dirty` set and the next edit,
    // Continue, or Exit will try again. Do not surface toast noise mid-typing.
    void save().catch(() => undefined);
  }, AUTOSAVE_MS);
}

type FounderState = {
  profile: FounderProfile;
  step: Step;
  /** Set when the user tries to advance with an incomplete step. */
  touched: boolean;
  deckError: boolean;
  assessment: Assessment | null;
  /** True once the stored profile has been read back (or found not to exist). */
  loaded: boolean;
  /** True when the form holds edits the server has not been told about. */
  dirty: boolean;
  /** True while a save request is in flight. */
  saving: boolean;
  /**
   * Answers the server had no field for on the last save. Surface these — they
   * were typed by a person and are not being stored.
   */
  unmapped: UnmappedAnswer[];
  /** Fields the server still needs for a strong audit. */
  missingFields: string[];

  /** Reads the saved profile back, so onboarding resumes where it stopped. */
  load(): Promise<void>;
  /** Persists the form. Returns what the server stored and what it refused. */
  save(): Promise<SaveResult>;

  // -- the real audit ------------------------------------------------------
  /** The run being watched, or the most recent one. */
  run: AuditRun | null;
  /** The finished report for `run`, once it succeeded. */
  report: AuditReport | null;
  /** Whatever stopped the audit being requested or read. */
  auditError: unknown;

  /** Saves, queues an audit, and polls it to a terminal state. */
  runAudit(): Promise<void>;
  /** Picks the newest run back up — an audit outlives the screen that started it. */
  resumeAudit(): Promise<void>;
  /**
   * Reads the newest run and its report, without polling.
   *
   * For screens that only want to *show* the latest state — the dashboard —
   * rather than wait on one. `resumeAudit` keeps polling until the run
   * finishes, which is right on the results screen and wrong on a tab
   * somebody may sit on for a while.
   */
  loadLatestAudit(): Promise<void>;

  setField<K extends keyof FounderProfile>(key: K, value: FounderProfile[K]): void;
  setStep(step: Step): void;
  markTouched(): void;
  uploadDeck(filename: string): void;
  failUpload(): void;
  clearDeckError(): void;
  reset(): void;

  /**
   * Provisional score computed on the device from what has been entered.
   * A heuristic over the form, not an audit — the results screen labels it so.
   */
  liveAssessment(): Assessment;
  /**
   * Sends the profile for a real audit. Resolves to `null` while the audit
   * engine does not exist, which leaves `assessment` unset and keeps the
   * results screen on its provisional estimate rather than inventing a verdict.
   */
  submit(): Promise<Assessment | null>;
};

/**
 * Which fields each onboarding step requires before it will advance.
 *
 * Deliberately close to the set the *server* needs before it will run an audit
 * (`description`, `business_model`, `team_size`, and monthly revenue, costs and
 * cash). Letting someone finish onboarding and only then discover their
 * profile cannot be audited would be the worst version of this.
 *
 * Everything else stays optional. A half-known profile is the normal case, not
 * an error — extraction fills gaps from documents, and thin data earns a
 * provisional verdict rather than a false one.
 */
const REQUIRED: Record<Step, (keyof FounderProfile)[]> = {
  1: ['company', 'sector', 'location', 'year', 'description', 'businessModel'],
  2: ['stage', 'revenue', 'costs', 'cash'],
  3: [],
  // Market and plan is entirely optional to the server, so it does not gate.
  // These are the questions that most improve a verdict and the ones founders
  // are least able to answer on the spot; blocking on them would cost more
  // completed assessments than it would gain in evidence.
  4: [],
  5: ['founders', 'teamSize'],
};

export function isStepValid(profile: FounderProfile, step: Step): boolean {
  return REQUIRED[step].every((k) => String(profile[k]).trim() !== '');
}

/**
 * True once every step has the answers the server needs to audit.
 *
 * This is what "has taken the assessment" means when there is no audit run to
 * point at — a founder who filled the form before the audit engine could run
 * it still has a profile worth scoring provisionally.
 */
export function isAssessmentComplete(profile: FounderProfile): boolean {
  return ([1, 2, 3, 4, 5] as Step[]).every((step) => isStepValid(profile, step));
}

/**
 * First step that still lacks a required answer — where onboarding should reopen.
 * When every step is complete, land on the last one so the founder can revise.
 */
export function firstIncompleteStep(profile: FounderProfile): Step {
  for (const step of [1, 2, 3, 4, 5] as Step[]) {
    if (!isStepValid(profile, step)) return step;
  }
  return 5;
}

/** The slice of the store the audit helpers below write to. */
type AuditSet = (partial: Partial<FounderState>) => void;

/**
 * Reads the report for a finished run.
 *
 * A `failed` run has no report to fetch — asking for one is an error, not an
 * empty result — so the failure is surfaced from the run itself, where the
 * server put a code and a message.
 */
async function loadReport(run: AuditRun, set: AuditSet): Promise<void> {
  if (run.status !== 'succeeded') {
    set({
      auditError: new Error(
        run.errorMessage ?? 'The audit did not finish. Try running it again.',
      ),
    });
    return;
  }
  set({ report: await api.getAuditReport(run.id) });
}

/**
 * Polls one run until it reaches a terminal state.
 *
 * Gives up after `POLL_TIMEOUT_MS` — which stops the *polling*, not the audit.
 * The run keeps going server-side and `resumeAudit` collects it later, so the
 * timeout costs a wait rather than a result.
 */
async function pollToFinish(
  run: AuditRun,
  set: AuditSet,
  get: () => FounderState,
): Promise<void> {
  const deadline = Date.now() + POLL_TIMEOUT_MS;
  let current = run;

  while (!isAuditFinished(current.status)) {
    if (Date.now() > deadline) return;
    await wait(POLL_INTERVAL_MS);
    // Another run may have been started meanwhile (the founder edited and
    // re-ran). Stop polling the one nobody is watching any more.
    if (get().run?.id !== current.id) return;
    current = await api.getAuditRun(current.id);
    set({ run: current });
  }

  await loadReport(current, set);
}

export const useFounder = create<FounderState>((set, get) => ({
  profile: { ...EMPTY_PROFILE },
  step: 1,
  touched: false,
  deckError: false,
  assessment: null,
  loaded: false,
  dirty: false,
  saving: false,
  unmapped: [],
  missingFields: [],
  run: null,
  report: null,
  auditError: null,

  setField(key, value) {
    editRevision += 1;
    set((s) => ({ profile: { ...s.profile, [key]: value }, dirty: true }));
    scheduleAutosave(() => get().save());
  },

  setStep(step) {
    set({ step, touched: false });
  },

  markTouched() {
    set({ touched: true });
  },

  uploadDeck(filename) {
    editRevision += 1;
    set((s) => ({ profile: { ...s.profile, deck: filename }, deckError: false, dirty: true }));
    scheduleAutosave(() => get().save());
  },

  failUpload() {
    set({ deckError: true });
  },

  clearDeckError() {
    set({ deckError: false });
  },

  reset() {
    clearAutosaveTimer();
    editRevision = 0;
    saveChain = Promise.resolve();
    set({
      profile: { ...EMPTY_PROFILE },
      step: 1,
      touched: false,
      deckError: false,
      assessment: null,
      loaded: false,
      dirty: false,
      saving: false,
      unmapped: [],
      missingFields: [],
      run: null,
      report: null,
      auditError: null,
    });
  },

  liveAssessment() {
    return assess(get().profile);
  },

  async load() {
    try {
      const stored = await api.getProfile();
      // Only adopt a stored profile over an untouched form. Someone who has
      // started typing must not have it replaced underneath them by a slow
      // request that resolves mid-edit.
      if (stored && !get().dirty) {
        set({
          profile: stored,
          step: firstIncompleteStep(stored),
          loaded: true,
        });
      } else set({ loaded: true });
    } catch {
      // **`loaded` is set whatever happens, and that is the point.** It means
      // "we have finished trying", not "we succeeded" -- the form is gated on
      // it, so leaving it false on a failure freezes onboarding on an empty
      // form with no way forward.
      //
      // The case that actually bites: a founder who has just signed up is
      // `pending_verification`, and the server answers `/v1/startups/me` with
      // 403 until they confirm their address. That is the *normal* state for
      // someone reaching this screen for the first time, not an error, and it
      // used to leave the company-name suggestion permanently suppressed.
      //
      // Nothing is lost by continuing. A blank form cannot overwrite stored
      // answers, because `toWireProfile` omits blanks rather than sending
      // nulls, and saving is create-then-update, so the next save reconciles.
      set({ loaded: true });
    }
  },

  async save() {
    clearAutosaveTimer();

    // Persist separately from the audit, and first: an audit that fails to
    // queue must not also cost the founder their answers.
    const run = async (): Promise<SaveResult> => {
      if (!get().dirty) {
        return {
          profile: get().profile,
          unmapped: get().unmapped,
          missingFields: get().missingFields,
        };
      }

      const revision = editRevision;
      const toSave = get().profile;
      set({ saving: true });
      try {
        const result = await api.saveProfile(toSave);
        const superseded = editRevision !== revision;
        set((s) => ({
          // Keep local edits that landed while the request was in flight.
          profile: superseded ? s.profile : result.profile,
          unmapped: result.unmapped,
          missingFields: result.missingFields,
          dirty: superseded,
          loaded: true,
          saving: false,
        }));
        // Another keystroke arrived mid-save — schedule a follow-up write.
        if (superseded) scheduleAutosave(() => get().save());
        return result;
      } catch (error) {
        set({ saving: false });
        throw error;
      }
    };

    const next = saveChain.then(run, run);
    saveChain = next.then(
      () => undefined,
      () => undefined,
    );
    return next;
  },

  async runAudit() {
    set({ auditError: null, report: null });
    try {
      await get().save();
      const queued = await api.requestAudit();
      set({ run: queued });
      await pollToFinish(queued, set, get);
    } catch (error) {
      set({ auditError: error });
    }
  },

  async loadLatestAudit() {
    try {
      const runs = await api.listAuditRuns();
      const latest = runs[0];
      if (!latest) return;
      set({ run: latest });
      if (isAuditFinished(latest.status)) await loadReport(latest, set);
    } catch {
      // Silent on purpose. This runs on the dashboard opening, where the
      // common failure is the 403 an unverified account gets on every route —
      // a normal state, not something to put an error panel in front of
      // somebody who did not ask for an audit just now.
    }
  },

  async resumeAudit() {
    // An audit takes minutes and outlives the screen that started it. Closing
    // the app mid-run must not lose the result.
    try {
      const runs = await api.listAuditRuns();
      const latest = runs[0];
      if (!latest) return;
      set({ run: latest });
      if (isAuditFinished(latest.status)) await loadReport(latest, set);
      else await pollToFinish(latest, set, get);
    } catch (error) {
      set({ auditError: error });
    }
  },

  async submit() {
    // Save first. If scoring is unavailable the answers still survive.
    const saved = await get()
      .save()
      .catch((error: unknown) => {
      if (isUnavailable(error)) return null;
      throw error;
    });

    try {
      const result = await api.submitAssessment(saved ? saved.profile : get().profile);
      set({ assessment: result });
      return result;
    } catch (error) {
      // No audit engine yet: fall through to the provisional estimate rather
      // than blocking the founder on a stage of the product that does not exist.
      if (isUnavailable(error)) return null;
      throw error;
    }
  },
}));
