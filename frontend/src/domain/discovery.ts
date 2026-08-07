/**
 * What an investor may see of a startup, before any introduction.
 *
 * **This is a much thinner thing than `Company` in `domain/types.ts`**, and
 * that is the server enforcing a rule, not an omission to work around. The
 * summary tier carries the name, the market, and the two verdicts — no MRR, no
 * growth rate, no margin, no LTV/CAC, no runway, no team, no memo, no risk
 * flags. Every one of those is full-report material and reaches an investor
 * only after an admin reveal (T4.6).
 *
 * So `Company` cannot be built from this, and nothing here should try. The
 * dealflow screens were designed against the prototype's seed data and assume
 * the richer shape; reconciling them is F4.2, and it is a design question
 * ("what does a card show when there is no MRR to show?") before it is a
 * coding one.
 */

import type { ServerStage } from '@/api/profile-mapping';

/**
 * A verdict at investor tier: the answer and nothing else.
 *
 * No rationale and no sufficiency — the founder's report has those; this does
 * not. `score` is nullable for the same reason it is on the founder's side:
 * the audit could not always reach a number, and a `0` would assert one.
 */
export type DiscoveryVerdict = {
  scope: string;
  level: string;
  score: number | null;
};

export type DiscoveredStartup = {
  startupId: string;
  name: string | null;
  sector: string | null;
  stage: ServerStage | null;
  /** ISO 3166-1 alpha-2. */
  country: string | null;
  /** Which audit produced these verdicts. */
  auditRunId: string;
  rubricVersion: string;
  fundability: DiscoveryVerdict;
  saleability: DiscoveryVerdict;
  publishedAt: string | null;
};

export type DiscoveryPage = {
  items: DiscoveredStartup[];
  total: number;
  limit: number;
  offset: number;
};

/**
 * The filters the server actually supports.
 *
 * Deliberately narrower than `DealflowQuery`, which carries a free-text query,
 * a minimum score, a VC/PE match type and four sort orders — none of which
 * `/v1/discover` accepts. Filtering client-side to make up the difference would
 * mean fetching rows the investor was not meant to receive in order to hide
 * them again, which defeats the tier.
 */
export type DiscoveryQuery = {
  sector?: string;
  stage?: ServerStage;
  /** ISO 3166-1 alpha-2. */
  country?: string;
  limit?: number;
  offset?: number;
};
