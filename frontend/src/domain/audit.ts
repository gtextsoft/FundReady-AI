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
    // Backend synthesis emits `ready` / `not_yet` / `provisional` /
    // `insufficient_data`. Older labels kept for forward compatibility.
    ready: 'Ready',
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

/** True when the audit cleared the bar for that scope. */
export function isReady(verdict: Verdict): boolean {
  return verdict.level === 'ready' || verdict.level === 'fundable' || verdict.level === 'saleable';
}

/**
 * Rubric v1 dimensions — titles mirror the backend catalog so the breakdown
 * can list every scored area, not only ones that happen to have an action.
 */
export type RubricScope = 'both' | 'fundability' | 'saleability';

export type RubricDimension = {
  key: string;
  title: string;
  question: string;
  scope: RubricScope;
};

export const RUBRIC_DIMENSIONS: readonly RubricDimension[] = [
  {
    key: 'financial_health',
    title: 'Financial health',
    question: 'Can this business fund its own operations, and for how long?',
    scope: 'both',
  },
  {
    key: 'unit_economics',
    title: 'Unit economics',
    question: 'Does each customer earn more than they cost to acquire?',
    scope: 'both',
  },
  {
    key: 'traction',
    title: 'Traction',
    question: 'Is demand real, growing, and visible outside the founder\'s word?',
    scope: 'both',
  },
  {
    key: 'market_opportunity',
    title: 'Market opportunity',
    question: 'Is the reachable market large enough to matter?',
    scope: 'both',
  },
  {
    key: 'team',
    title: 'Team',
    question: 'Can this team ship what the plan requires?',
    scope: 'both',
  },
  {
    key: 'legal_and_ip',
    title: 'Legal & IP',
    question: 'Does the company own what it sells?',
    scope: 'both',
  },
  {
    key: 'data_integrity',
    title: 'Data integrity',
    question: 'Do the figures agree with each other and with the documents?',
    scope: 'both',
  },
  {
    key: 'scalability',
    title: 'Scalability',
    question: 'Does more capital buy growth, or just more of the same cost?',
    scope: 'fundability',
  },
  {
    key: 'owner_independence',
    title: 'Owner independence',
    question: 'Would the business keep running if the founder stepped away?',
    scope: 'saleability',
  },
  {
    key: 'transferability',
    title: 'Transferability',
    question: 'Could contracts and relationships survive a change of owner?',
    scope: 'saleability',
  },
  {
    key: 'revenue_durability',
    title: 'Revenue durability',
    question: 'How sticky and recurring is the revenue an acquirer would buy?',
    scope: 'saleability',
  },
] as const;

export type DimensionRowStatus = 'missing' | 'priority' | 'needs_work' | 'evidenced';

export type DimensionRow = {
  key: string;
  title: string;
  question: string;
  scope: RubricScope;
  status: DimensionRowStatus;
  score: number | null;
  action: string | null;
};

function dimensionTitle(key: string): string {
  return RUBRIC_DIMENSIONS.find((d) => d.key === key)?.title ?? key.replace(/_/g, ' ');
}

/**
 * Full per-dimension scoreboard derived from the founder report.
 *
 * The API does not return a `scores[]` array — scores ride on action items, and
 * evidenced/unevidenced lists tell us coverage. This stitches those into one
 * row per rubric dimension so the UI can show a proper breakdown.
 */
export function buildDimensionRows(report: AuditReport): DimensionRow[] {
  const missing = new Set([
    ...report.fundability.unevidencedDimensions,
    ...report.saleability.unevidencedDimensions,
  ]);
  const evidenced = new Set([
    ...report.fundability.evidencedDimensions,
    ...report.saleability.evidencedDimensions,
  ]);

  const actionsByDim = new Map<string, AuditAction[]>();
  for (const item of report.actionPlan) {
    const list = actionsByDim.get(item.dimension) ?? [];
    list.push(item);
    actionsByDim.set(item.dimension, list);
  }

  const knownKeys = new Set(RUBRIC_DIMENSIONS.map((d) => d.key));
  // Surface any server dimension that is not in the local catalog (future rubric).
  const extras = [...missing, ...evidenced, ...actionsByDim.keys()].filter((k) => !knownKeys.has(k));

  const catalog: RubricDimension[] = [
    ...RUBRIC_DIMENSIONS,
    ...extras.map((key) => ({
      key,
      title: dimensionTitle(key),
      question: '',
      scope: 'both' as RubricScope,
    })),
  ];

  return catalog.map((dim) => {
    const actions = actionsByDim.get(dim.key) ?? [];
    const score =
      actions.map((a) => a.dimensionScore).find((s): s is number => s !== null) ?? null;
    const isMissing = missing.has(dim.key);
    const isPriority = actions.some((a) => a.isPriority);
    const status: DimensionRowStatus = isMissing
      ? 'missing'
      : isPriority
        ? 'priority'
        : actions.length > 0
          ? 'needs_work'
          : evidenced.has(dim.key)
            ? 'evidenced'
            : 'missing';

    return {
      key: dim.key,
      title: dim.title,
      question: dim.question,
      scope: dim.scope,
      status,
      score: isMissing ? null : score,
      action: actions[0]?.action ?? null,
    };
  });
}

export type InvestorTalkAdvice = {
  /** Short answer shown as the eyebrow. */
  answer: 'Yes' | 'Not yet' | 'Maybe' | 'Too soon to say';
  /** One-line headline. */
  title: string;
  /** Supporting copy. */
  body: string;
};

/** Plain-language answer to "should I talk to investors?" from the fundability verdict. */
export function investorTalkAdvice(fundability: Verdict): InvestorTalkAdvice {
  if (isInsufficient(fundability)) {
    return {
      answer: 'Too soon to say',
      title: 'Get more evidence on the record first',
      body: 'The audit could not form a fundability view from what you submitted. Fill the missing dimensions and re-run before spending warm intros.',
    };
  }
  if (isReady(fundability)) {
    return {
      answer: 'Yes',
      title: 'You clear the screening floor',
      body: 'Start conversations where the match is real. Keep the PDF handy — investors on this platform see a summary; the full breakdown is yours to share.',
    };
  }
  if (fundability.level === 'provisional') {
    return {
      answer: 'Maybe',
      title: 'Only with people who already know you',
      body: 'A provisional score means the story can still move either way. Close the priority gaps before a cold outreach; a soft no is expensive to reverse.',
    };
  }
  return {
    answer: 'Not yet',
    title: 'Close the gaps before you take meetings',
    body: 'Talking to investors now mostly burns introductions. Work the priority actions below, upload evidence, and re-run the audit when the numbers move.',
  };
}
