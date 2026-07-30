import { create } from 'zustand';
import { api, isUnavailable } from '@/api';
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

/** Which fields each onboarding step requires before it will advance. */
const REQUIRED: Record<Step, (keyof FounderProfile)[]> = {
  1: ['company', 'sector', 'location', 'year'],
  2: ['stage', 'revenue', 'growth'],
  3: ['tam', 'margin'],
  4: ['founders', 'technical'],
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

  setField(key, value) {
    set((s) => ({ profile: { ...s.profile, [key]: value } }));
  },

  setStep(step) {
    set({ step, touched: false });
  },

  markTouched() {
    set({ touched: true });
  },

  uploadDeck(filename) {
    set((s) => ({ profile: { ...s.profile, deck: filename }, deckError: false }));
  },

  failUpload() {
    set({ deckError: true });
  },

  clearDeckError() {
    set({ deckError: false });
  },

  reset() {
    set({ profile: { ...EMPTY_PROFILE }, step: 1, touched: false, deckError: false, assessment: null });
  },

  liveAssessment() {
    return assess(get().profile);
  },

  async submit() {
    try {
      const result = await api.submitAssessment(get().profile);
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
