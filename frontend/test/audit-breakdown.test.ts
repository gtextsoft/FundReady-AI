import {
  buildDimensionRows,
  investorTalkAdvice,
  type AuditReport,
  type Verdict,
} from '@/domain/audit';

const verdict = (partial: Partial<Verdict>): Verdict => ({
  scope: 'fundability',
  level: 'not_yet',
  score: 52,
  sufficiency: 'partial',
  rationale: 'Needs work.',
  evidencedDimensions: ['financial_health'],
  unevidencedDimensions: ['market_opportunity'],
  ...partial,
});

const report = (partial: Partial<AuditReport> = {}): AuditReport => ({
  rubricVersion: 'v1',
  dataIntegrityScore: 'high',
  fundability: verdict({ scope: 'fundability' }),
  saleability: verdict({
    scope: 'saleability',
    evidencedDimensions: ['financial_health'],
    unevidencedDimensions: ['owner_independence'],
  }),
  findings: [],
  actionPlan: [
    {
      dimension: 'unit_economics',
      action: 'Include sales salaries in CAC.',
      dimensionScore: 40,
      isPriority: true,
    },
  ],
  ...partial,
});

describe('buildDimensionRows', () => {
  it('lists every rubric dimension with a status', () => {
    const rows = buildDimensionRows(report());
    expect(rows.length).toBeGreaterThanOrEqual(11);
    expect(rows.find((r) => r.key === 'financial_health')?.status).toBe('evidenced');
    expect(rows.find((r) => r.key === 'market_opportunity')?.status).toBe('missing');
    expect(rows.find((r) => r.key === 'unit_economics')?.status).toBe('priority');
    expect(rows.find((r) => r.key === 'unit_economics')?.score).toBe(40);
  });
});

describe('investorTalkAdvice', () => {
  it('says yes when fundability is ready', () => {
    expect(investorTalkAdvice(verdict({ level: 'ready', score: 78 })).answer).toBe('Yes');
  });

  it('says not yet when fundability is not_yet', () => {
    expect(investorTalkAdvice(verdict({ level: 'not_yet', score: 48 })).answer).toBe('Not yet');
  });

  it('says too soon when the audit could not score', () => {
    expect(
      investorTalkAdvice(verdict({ level: 'insufficient_data', score: null })).answer,
    ).toBe('Too soon to say');
  });
});
