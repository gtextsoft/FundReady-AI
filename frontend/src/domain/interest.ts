/**
 * An investor's expression of interest, as the brokerage API returns it.
 *
 * Approval is not a reveal: the founder never sees the note, and a full report
 * only appears once SACI opens a run (revealed_run_ids).
 */

export type InterestStatus = 'pending' | 'approved' | 'declined' | 'withdrawn';

export type Interest = {
  id: string;
  startupId: string;
  status: InterestStatus;
  note: string | null;
  createdAt: string;
  decidedAt: string | null;
  revealedRunIds: string[];
};
