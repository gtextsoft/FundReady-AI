import { create } from 'zustand';
import { api, isUnavailable, type SaveResult } from '@/api';
import type { UnmappedAnswer } from '@/api/profile-mapping';
import { assess } from '@/domain/scoring';
import { EMPTY_PROFILE, type Assessment, type FounderProfile } from '@/domain/types';

export type Step = 1 | 2 | 3 | 4;

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
  /**
   * Answers the server had no field for on the last save. Surface these — they
   * were typed by a person and are not being stored.
   */
  unmapped: UnmappedAnswer[];

  /** Reads the saved profile back, so onboarding resumes where it stopped. */
  load(): Promise<void>;
  /** Persists the form. Returns what the server stored and what it refused. */
  save(): Promise<SaveResult>;

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
  4: ['founders', 'teamSize'],
};

export function isStepValid(profile: FounderProfile, step: Step): boolean {
  return REQUIRED[step].every((k) => String(profile[k]).trim() !== '');
}

export const useFounder = create<FounderState>((set, get) => ({
  profile: { ...EMPTY_PROFILE },
  step: 1,
  touched: false,
  deckError: false,
  assessment: null,
  loaded: false,
  dirty: false,
  unmapped: [],

  setField(key, value) {
    set((s) => ({ profile: { ...s.profile, [key]: value }, dirty: true }));
  },

  setStep(step) {
    set({ step, touched: false });
  },

  markTouched() {
    set({ touched: true });
  },

  uploadDeck(filename) {
    set((s) => ({ profile: { ...s.profile, deck: filename }, deckError: false, dirty: true }));
  },

  failUpload() {
    set({ deckError: true });
  },

  clearDeckError() {
    set({ deckError: false });
  },

  reset() {
    set({
      profile: { ...EMPTY_PROFILE },
      step: 1,
      touched: false,
      deckError: false,
      assessment: null,
      loaded: false,
      dirty: false,
      unmapped: [],
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
      if (stored && !get().dirty) set({ profile: stored, loaded: true });
      else set({ loaded: true });
    } catch (error) {
      if (isUnavailable(error)) {
        set({ loaded: true });
        return;
      }
      throw error;
    }
  },

  async save() {
    // Persisted before scoring, and separately from it: the audit engine does
    // not exist yet, and losing a founder's answers because the *scoring* is
    // unbuilt would be the worst of both.
    const result = await api.saveProfile(get().profile);
    set({ profile: result.profile, unmapped: result.unmapped, dirty: false, loaded: true });
    return result;
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
