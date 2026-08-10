import { create } from 'zustand';
import { api } from '@/api';
import type { ServerStage } from '@/api/profile-mapping';
import type { Interest } from '@/domain/interest';

type InvestorState = {
  /** Single sector filter — `/v1/discover` accepts one. */
  sector: string | null;
  stage: ServerStage | null;
  country: string | null;
  watchlist: string[];
  /** Startup ids the investor has already expressed interest in (this session + reloads). */
  interestedIds: string[];
  interests: Interest[];

  setSector(s: string | null): void;
  setStage(s: ServerStage | null): void;
  setCountry(c: string | null): void;
  clearFilters(): void;
  activeFilterCount(): number;

  loadWatchlist(): Promise<void>;
  toggleWatch(startupId: string): Promise<void>;
  loadInterests(): Promise<void>;
  expressInterest(startupId: string, note?: string): Promise<Interest>;
};

export const useInvestor = create<InvestorState>((set, get) => ({
  sector: null,
  stage: null,
  country: null,
  watchlist: [],
  interestedIds: [],
  interests: [],

  setSector(sector) {
    set({ sector });
  },
  setStage(stage) {
    set({ stage });
  },
  setCountry(country) {
    set({ country });
  },
  clearFilters() {
    set({ sector: null, stage: null, country: null });
  },
  activeFilterCount() {
    const s = get();
    return (s.sector ? 1 : 0) + (s.stage ? 1 : 0) + (s.country ? 1 : 0);
  },

  async loadWatchlist() {
    try {
      set({ watchlist: await api.getWatchlist() });
    } catch {
      set({ watchlist: [] });
    }
  },

  async toggleWatch(startupId) {
    const before = get().watchlist;
    const next = before.includes(startupId)
      ? before.filter((x) => x !== startupId)
      : [...before, startupId];
    set({ watchlist: next });
    try {
      set({ watchlist: await api.toggleWatch(startupId) });
    } catch {
      set({ watchlist: before });
    }
  },

  async loadInterests() {
    try {
      const interests = await api.listInterests();
      set({
        interests,
        interestedIds: interests.map((i) => i.startupId),
      });
    } catch {
      // Endpoint may 403 before email verify; leave local state alone.
    }
  },

  async expressInterest(startupId, note) {
    const interest = await api.expressInterest(startupId, note);
    set((s) => ({
      interests: [interest, ...s.interests.filter((i) => i.id !== interest.id)],
      interestedIds: s.interestedIds.includes(startupId)
        ? s.interestedIds
        : [...s.interestedIds, startupId],
    }));
    return interest;
  },
}));
