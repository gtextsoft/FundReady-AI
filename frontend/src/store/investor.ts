import { create } from 'zustand';
import { api } from '@/api';
import type { MatchType, SortKey } from '@/domain/types';

type InvestorState = {
  query: string;
  minScore: number;
  match: 'All' | MatchType;
  sectors: string[];
  stages: string[];
  sort: SortKey;
  page: number;
  watchlist: string[];
  /** Companies the user has already asked to be introduced to. */
  introRequested: string[];

  setQuery(q: string): void;
  setMinScore(n: number): void;
  setMatch(m: 'All' | MatchType): void;
  toggleSector(s: string): void;
  toggleStage(s: string): void;
  setSort(s: SortKey): void;
  setPage(p: number): void;
  clearFilters(): void;
  activeFilterCount(): number;

  loadWatchlist(): Promise<void>;
  toggleWatch(id: string): Promise<void>;
  requestIntro(id: string): Promise<void>;
};

export const useInvestor = create<InvestorState>((set, get) => ({
  query: '',
  minScore: 0,
  match: 'All',
  sectors: [],
  stages: [],
  sort: 'score',
  page: 1,
  watchlist: [],
  introRequested: [],

  setQuery(query) {
    set({ query, page: 1 });
  },
  setMinScore(minScore) {
    set({ minScore, page: 1 });
  },
  setMatch(match) {
    set({ match, page: 1 });
  },
  toggleSector(s) {
    set((st) => ({
      sectors: st.sectors.includes(s) ? st.sectors.filter((x) => x !== s) : [...st.sectors, s],
      page: 1,
    }));
  },
  toggleStage(s) {
    set((st) => ({
      stages: st.stages.includes(s) ? st.stages.filter((x) => x !== s) : [...st.stages, s],
      page: 1,
    }));
  },
  setSort(sort) {
    set({ sort, page: 1 });
  },
  setPage(page) {
    set({ page });
  },
  clearFilters() {
    set({ minScore: 0, match: 'All', sectors: [], stages: [], query: '', page: 1 });
  },
  activeFilterCount() {
    const s = get();
    return (s.minScore > 0 ? 1 : 0) + (s.match !== 'All' ? 1 : 0) + s.sectors.length + s.stages.length;
  },

  async loadWatchlist() {
    try {
      set({ watchlist: await api.getWatchlist() });
    } catch {
      // No watchlist endpoint yet. An empty list is the truth, not a guess.
      set({ watchlist: [] });
    }
  },

  async toggleWatch(id) {
    // Optimistic — the star should not wait on a round trip.
    const before = get().watchlist;
    const next = before.includes(id) ? before.filter((x) => x !== id) : [...before, id];
    set({ watchlist: next });
    try {
      set({ watchlist: await api.toggleWatch(id) });
    } catch {
      set({ watchlist: before });
    }
  },

  async requestIntro(id) {
    await api.requestIntroduction(id);
    set((s) => ({ introRequested: s.introRequested.includes(id) ? s.introRequested : [...s.introRequested, id] }));
  },
}));
