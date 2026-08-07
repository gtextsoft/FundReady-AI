/**
 * The real audit, as the server produces it.
 *
 * Kept deliberately separate from `Assessment` in `domain/types.ts`. That one
 * is the on-device heuristic ported from the design prototype — a score out of
 * 100 with weighted parts, VC/PE fit and a colour band. **The server's audit
 * has none of those things**, and reshaping one into the other would mean
 * inventing the difference: a `score` where the audit returned `null`, a band
 * label for a verdict that says `insufficient_data`.
 *
 * So they coexist, and the results screen renders whichever it has, saying
 * which. When the audit lands, the heuristic can go — see F2.1.
 */

/** Where an audit run has got to. Terminal states are `succeeded` and `failed`. */
export type AuditStatus = 'queued' | 'running' | 'succeeded' | 'failed';

export const AUDIT_TERMINAL: readonly AuditStatus[] = ['succeeded', 'failed'];

export function isAuditFinished(status: AuditStatus): boolean {
  return AUDIT_TERMINAL.includes(status);
}

/**
 * One run's lifecycle. **Status only — never the report.** The server splits
 * these deliberately, so polling for progress cannot leak the findings.
 */
export type AuditRun = {
  id: string;
  startupId: string;
  status: AuditStatus;
  rubricVersion: string;
  attempts: number;
  /** Set only when `status` is `failed`. */
  errorCode: string | null;
  errorMessage: string | null;
  createdAt: string;
  startedAt: string | null;
  completedAt: string | null;
};

/**
 * A verdict, at the tier the founder sees.
 *
 * `score` is nullable and that is load-bearing: a `null` means the audit could
 * not reach a number, which is materially different from a low one. Never
 * render it as 0.
 */
export type Verdict = {
  /** `fundability` or `saleability`. */
  scope: string;
  /** The answer, e.g. `fundable` / `not_yet` / `insufficient_data`. */
  level: string;
  score: number | null;
  /** How much of the rubric had evidence behind it. */
  sufficiency: string;
  rationale: string;
  evidencedDimensions: string[];
  unevidencedDimensions: string[];
};

/** Something in the submission that does not add up. */
export type AuditFinding = {
  code: string;
  severity: string;
  /** Which profile fields it concerns. */
  fields: string[];
  message: string;
};

/** One thing the founder can do to improve a verdict. */
export type AuditAction = {
  dimension: string;
  action: string;
  dimensionScore: number | null;
  isPriority: boolean;
};

/** The founder tier: their own audit, in full. */
export type AuditReport = {
  rubricVersion: string;
  /** How much the documents agreed with each other. A string, not a number. */
  dataIntegrityScore: string;
  fundability: Verdict;
  saleability: Verdict;
  findings: AuditFinding[];
  actionPlan: AuditAction[];
};

/**
 * Human-readable verdict labels.
 *
 * Unknown levels fall through to a de-snake-cased version of whatever the
 * server sent rather than to a default like "Not fundable" — the rubric is
 * versioned and can add levels, and guessing one wrong puts a verdict on
 * screen that the audit never reached.
 */
export function verdictLabel(level: string): string {
  const known: Record<string, string> = {
    fundable: 'Fundable',
    not_yet: 'Not yet',
    provisional: 'Provisional',
    insufficient_data: 'Not enough to tell',
    saleable: 'Saleable',
  };
  return known[level] ?? level.replace(/_/g, ' ').replace(/^\w/, (c) => c.toUpperCase());
}

/** True when the audit declined to reach a verdict for want of evidence. */
export function isInsufficient(verdict: Verdict): boolean {
  return verdict.level === 'insufficient_data' || verdict.score === null;
}
