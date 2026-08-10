import { Pressable, View } from 'react-native';
import { router } from 'expo-router';

import { Button } from '@/components/ui/button';
import { Eyebrow, Mono, Txt, TxtSemi } from '@/components/ui/text';
import { C } from '@/theme/tokens';
import {
  buildDimensionRows,
  investorTalkAdvice,
  isInsufficient,
  isReady,
  verdictLabel,
  type AuditFinding,
  type AuditReport,
  type AuditRun,
  type DimensionRow,
  type DimensionRowStatus,
  type Verdict,
} from '@/domain/audit';

/**
 * The real audit, rendered.
 *
 * The one rule this file exists to keep: **a verdict with no score is not a
 * zero.** The audit returns `score: null` when it could not tell, and a ring
 * showing 0 out of 100 would state a conclusion the audit explicitly declined
 * to reach. Those render as "Not enough to tell" with the reason, never as a
 * number.
 */

/** Colour by verdict level, muted for anything the audit was unsure about. */
function verdictColour(verdict: Verdict): string {
  if (isInsufficient(verdict)) return C.inkMuted;
  if (isReady(verdict)) return C.grn;
  if (verdict.level === 'provisional') return C.amb;
  return C.red;
}

const STATUS_META: Record<
  DimensionRowStatus,
  { label: string; color: string }
> = {
  missing: { label: 'MISSING', color: C.amb },
  priority: { label: 'PRIORITY', color: C.red },
  needs_work: { label: 'NEEDS WORK', color: C.amb },
  evidenced: { label: 'EVIDENCED', color: C.grn },
};

function ScoreBar({ score, color }: { score: number | null; color: string }) {
  const width = score === null ? 0 : Math.max(0, Math.min(100, score));
  return (
    <View className="mt-[8px] h-[4px] w-full overflow-hidden rounded-[2px] bg-surface-3">
      <View className="h-full rounded-[2px]" style={{ width: `${width}%`, backgroundColor: color }} />
    </View>
  );
}

function VerdictCard({ verdict, title }: { verdict: Verdict; title: string }) {
  const colour = verdictColour(verdict);
  const unknown = isInsufficient(verdict);

  return (
    <View className="flex-1 rounded-[12px] border border-line bg-surface-1 p-[14px]">
      <Eyebrow>{title}</Eyebrow>

      <View className="mb-[4px] mt-[10px] flex-row items-baseline gap-[6px]">
        {unknown ? (
          <TxtSemi className="text-[16px]" style={{ color: colour, letterSpacing: -0.3 }}>
            {verdictLabel(verdict.level)}
          </TxtSemi>
        ) : (
          <>
            <Mono className="text-[28px]" style={{ color: colour, letterSpacing: -1.2 }}>
              {verdict.score}
            </Mono>
            <Txt className="text-[11px] text-ink-faint">/ 100</Txt>
          </>
        )}
      </View>

      {unknown ? null : (
        <TxtSemi className="text-[12.5px]" style={{ color: colour }}>
          {verdictLabel(verdict.level)}
        </TxtSemi>
      )}

      <Txt className="mt-[8px] text-[11.5px] text-ink-faint" style={{ lineHeight: 17 }}>
        Evidence: {verdict.sufficiency.replace(/_/g, ' ')}
      </Txt>
    </View>
  );
}

function InvestorTalkCard({ report }: { report: AuditReport }) {
  const advice = investorTalkAdvice(report.fundability);
  const colour =
    advice.answer === 'Yes' ? C.grn : advice.answer === 'Not yet' ? C.red : C.amb;

  return (
    <View
      className="rounded-[12px] p-[14px]"
      style={{
        borderWidth: 1,
        borderColor: `${colour}40`,
        backgroundColor: advice.answer === 'Yes' ? 'rgba(12,206,107,0.06)' : 'rgba(245,166,35,0.06)',
      }}>
      <Mono className="text-[9px]" style={{ letterSpacing: 1.2, color: colour }}>
        SHOULD YOU TALK TO INVESTORS? · {advice.answer.toUpperCase()}
      </Mono>
      <TxtSemi className="mt-[8px] text-[15px]" style={{ letterSpacing: -0.3 }}>
        {advice.title}
      </TxtSemi>
      <Txt className="mt-[6px] text-[12.5px] text-ink-muted" style={{ lineHeight: 19 }}>
        {advice.body}
      </Txt>
      <Txt className="mt-[10px] text-[12px] text-ink-muted" style={{ lineHeight: 18 }}>
        {report.fundability.rationale}
      </Txt>
    </View>
  );
}

function DimensionRowView({ row }: { row: DimensionRow }) {
  const meta = STATUS_META[row.status];
  const barColor =
    row.status === 'evidenced' ? C.grn : row.status === 'priority' ? C.red : C.amb;

  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={`${row.title}, ${meta.label}`}
      onPress={() => router.push('/founder/tasks')}
      className="border-t border-line-soft py-[12px]">
      <View className="flex-row items-start justify-between gap-3">
        <View className="min-w-0 flex-1">
          <TxtSemi className="text-[13px] text-ink">{row.title}</TxtSemi>
          {row.question ? (
            <Txt className="mt-[3px] text-[11.5px] text-ink-faint" style={{ lineHeight: 16 }}>
              {row.question}
            </Txt>
          ) : null}
        </View>
        <View className="items-end">
          <Mono className="text-[9.5px]" style={{ color: meta.color, letterSpacing: 0.6 }}>
            {meta.label}
          </Mono>
          <Mono className="mt-[3px] text-[12px] text-ink">
            {row.score === null ? (row.status === 'evidenced' ? '✓' : '—') : `${row.score}`}
          </Mono>
        </View>
      </View>
      <ScoreBar score={row.status === 'evidenced' && row.score === null ? 100 : row.score} color={barColor} />
      {row.action ? (
        <Txt className="mt-[8px] text-[12px] text-ink-muted" style={{ lineHeight: 18 }}>
          → {row.action}
        </Txt>
      ) : row.status === 'missing' ? (
        <Txt className="mt-[8px] text-[12px] text-ink-muted" style={{ lineHeight: 18 }}>
          → No evidence submitted for this dimension yet.
        </Txt>
      ) : null}
    </Pressable>
  );
}

function DimensionBreakdown({ report }: { report: AuditReport }) {
  const rows = buildDimensionRows(report);
  const fundability = rows.filter((r) => r.scope === 'both' || r.scope === 'fundability');
  const saleabilityOnly = rows.filter((r) => r.scope === 'saleability');

  return (
    <View className="rounded-[12px] border border-line bg-surface-1 p-[14px]">
      <View className="mb-1 flex-row items-center justify-between">
        <Eyebrow>Dimension breakdown</Eyebrow>
        <Pressable
          accessibilityRole="link"
          accessibilityLabel="Open readiness tasks"
          onPress={() => router.push('/founder/tasks')}
          hitSlop={8}>
          <Mono className="text-[10px]" style={{ color: C.blue }}>
            OPEN TASKS →
          </Mono>
        </Pressable>
      </View>
      <Txt className="mt-[8px] text-[11.5px] text-ink-faint" style={{ lineHeight: 17 }}>
        Every rubric area, scored where evidence exists. Tap a row to work the matching tasks.
      </Txt>

      <Mono className="mb-1 mt-[16px] text-[9px] text-ink-faint" style={{ letterSpacing: 0.8 }}>
        FUNDABILITY
      </Mono>
      {fundability.map((row) => (
        <DimensionRowView key={row.key} row={row} />
      ))}

      {saleabilityOnly.length > 0 ? (
        <>
          <Mono className="mb-1 mt-[18px] text-[9px] text-ink-faint" style={{ letterSpacing: 0.8 }}>
            SALEABILITY ONLY
          </Mono>
          {saleabilityOnly.map((row) => (
            <DimensionRowView key={row.key} row={row} />
          ))}
        </>
      ) : null}
    </View>
  );
}

function FindingsSection({ findings }: { findings: AuditFinding[] }) {
  if (findings.length === 0) return null;

  const order = ['certain', 'likely', 'possible', 'high', 'medium', 'low', 'info'];
  const groups = new Map<string, AuditFinding[]>();
  for (const finding of findings) {
    const key = finding.severity || 'info';
    const list = groups.get(key) ?? [];
    list.push(finding);
    groups.set(key, list);
  }
  const severities = [...groups.keys()].sort((a, b) => {
    const ai = order.indexOf(a);
    const bi = order.indexOf(b);
    return (ai === -1 ? 99 : ai) - (bi === -1 ? 99 : bi);
  });

  return (
    <View className="rounded-[12px] border border-line bg-surface-1 p-[14px]">
      <Eyebrow>Findings</Eyebrow>
      <Txt className="mt-[8px] text-[11.5px] text-ink-faint" style={{ lineHeight: 17 }}>
        Things in your submission that do not add up. Fix these before the next run.
      </Txt>
      {severities.map((severity) => (
        <View key={severity} className="mt-[12px]">
          <Mono className="mb-[6px] text-[9.5px] text-ink-faint" style={{ letterSpacing: 0.8 }}>
            {severity.toUpperCase()}
          </Mono>
          {(groups.get(severity) ?? []).map((finding, index) => (
            <View key={`${finding.code}-${index}`} className="mb-[10px]">
              <View className="mb-[4px] flex-row items-center gap-2">
                <View
                  className="h-[5px] w-[5px] rounded-full"
                  style={{
                    backgroundColor:
                      severity === 'certain' || severity === 'high' ? C.red : C.amb,
                  }}
                />
                <TxtSemi className="flex-1 text-[12.5px] text-ink">{finding.message}</TxtSemi>
              </View>
              {finding.fields.length > 0 ? (
                <Mono className="ml-[13px] text-[10px] text-ink-faint">
                  {finding.fields.join(' · ')}
                </Mono>
              ) : null}
            </View>
          ))}
        </View>
      ))}
    </View>
  );
}

function PriorityActions({ report }: { report: AuditReport }) {
  const priorities = report.actionPlan.filter((a) => a.isPriority);
  const rest = report.actionPlan.filter((a) => !a.isPriority);
  if (priorities.length === 0 && rest.length === 0) return null;

  const show = [...priorities, ...rest].slice(0, 6);

  return (
    <View className="rounded-[12px] border border-line bg-surface-1 p-[14px]">
      <Eyebrow>What to do next</Eyebrow>
      <Txt className="mt-[8px] text-[11.5px] text-ink-faint" style={{ lineHeight: 17 }}>
        Priority items first. Completing these with evidence is what moves the next audit.
      </Txt>
      {show.map((item, index) => (
        <Pressable
          key={`${item.dimension}-${index}`}
          accessibilityRole="button"
          onPress={() => router.push('/founder/tasks')}
          className="mt-[12px] flex-row gap-[9px] border-t border-line-soft pt-[10px]">
          <Mono
            className="text-[10px]"
            style={{ color: item.isPriority ? C.amb : C.inkFaint, lineHeight: 18 }}>
            {item.isPriority ? '!' : '·'}
          </Mono>
          <View className="min-w-0 flex-1">
            <Mono className="text-[9.5px] text-ink-faint" style={{ letterSpacing: 0.6 }}>
              {item.dimension.replace(/_/g, ' ').toUpperCase()}
              {item.dimensionScore !== null ? ` · ${item.dimensionScore}/100` : ''}
            </Mono>
            <Txt className="mt-[3px] text-[12.5px] text-ink" style={{ lineHeight: 19 }}>
              {item.action}
            </Txt>
          </View>
        </Pressable>
      ))}
      {report.actionPlan.length > show.length ? (
        <Pressable
          accessibilityRole="link"
          onPress={() => router.push('/founder/tasks')}
          className="mt-[12px]">
          <Mono className="text-[10px]" style={{ color: C.blue }}>
            +{report.actionPlan.length - show.length} MORE IN TASKS →
          </Mono>
        </Pressable>
      ) : null}
    </View>
  );
}

/** While the audit is queued or running. */
export function AuditPending({ run }: { run: AuditRun }) {
  return (
    <View
      className="mb-4 rounded-[12px] p-[13px]"
      style={{ borderWidth: 1, borderStyle: 'dashed', borderColor: C.lineDash }}>
      <Mono className="text-[9px]" style={{ letterSpacing: 1.2, color: C.blue }}>
        {run.status === 'queued' ? 'AUDIT QUEUED' : 'AUDIT RUNNING'}
      </Mono>
      <Txt className="mt-[7px] text-[12.5px] text-ink-muted" style={{ lineHeight: 19 }}>
        Your submission is being audited against rubric {run.rubricVersion}. This takes a few
        minutes. The PDF download unlocks when it finishes — you can leave and come back.
      </Txt>
    </View>
  );
}

/** When the run reached `failed`. */
export function AuditFailed({ run }: { run: AuditRun }) {
  return (
    <View
      className="mb-4 rounded-[12px] p-[13px]"
      style={{ borderWidth: 1, borderColor: '#4a1d1d', backgroundColor: 'rgba(255,77,79,0.08)' }}>
      <Mono className="text-[9px]" style={{ letterSpacing: 1.2, color: C.red }}>
        AUDIT FAILED
      </Mono>
      <Txt className="mt-[7px] text-[12.5px] text-ink-muted" style={{ lineHeight: 19 }}>
        {run.errorMessage ?? 'The audit did not finish. Nothing has been scored.'}
      </Txt>
    </View>
  );
}

export function AuditReportView({
  report,
  onDownloadPdf,
  pdfBusy,
  pdfError,
}: {
  report: AuditReport;
  onDownloadPdf?: () => void;
  pdfBusy?: boolean;
  pdfError?: string | null;
}) {
  return (
    <View className="gap-4">
      <View className="flex-row items-center justify-between">
        <Mono className="text-[9px]" style={{ letterSpacing: 1.2, color: C.grn }}>
          FUNDREADY AI AUDIT · {report.rubricVersion}
        </Mono>
        <Mono className="text-[9px] text-ink-faint" style={{ letterSpacing: 0.6 }}>
          INTEGRITY {report.dataIntegrityScore}
        </Mono>
      </View>

      {onDownloadPdf ? (
        <View>
          <Button
            label={pdfBusy ? 'Preparing PDF…' : 'Download full audit PDF'}
            variant="primary"
            onPress={onDownloadPdf}
            disabled={pdfBusy}
            loading={pdfBusy}
          />
          {pdfError ? (
            <Txt className="mt-2 text-[12px] text-ink-muted" style={{ lineHeight: 18 }}>
              {pdfError}
            </Txt>
          ) : (
            <Txt className="mt-2 text-center text-[11px] text-ink-faint">
              Scoreboard, findings and action plan — the copy you can share.
            </Txt>
          )}
        </View>
      ) : null}

      <View className="flex-row gap-[10px]">
        <VerdictCard verdict={report.fundability} title="Fundability" />
        <VerdictCard verdict={report.saleability} title="Saleability" />
      </View>

      <InvestorTalkCard report={report} />

      <DimensionBreakdown report={report} />
      <FindingsSection findings={report.findings} />
      <PriorityActions report={report} />
    </View>
  );
}
