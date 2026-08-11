import { View } from 'react-native';

import { Eyebrow, Mono, Txt, TxtSemi } from '@/components/ui/text';
import { C } from '@/theme/tokens';
import {
  isInsufficient,
  verdictLabel,
  type AuditReport,
  type AuditRun,
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
  if (isInsufficient(verdict)) return C.boneSecondary;
  if (verdict.level === 'fundable' || verdict.level === 'saleable') return C.signal;
  if (verdict.level === 'provisional') return C.flag;
  return C.alert;
}

function VerdictPanel({ verdict, title }: { verdict: Verdict; title: string }) {
  const colour = verdictColour(verdict);
  const unknown = isInsufficient(verdict);

  return (
    <View className="flex-1 rounded-[12px] border border-graphite bg-carbon-low p-[14px]">
      <Eyebrow>{title}</Eyebrow>

      <View className="mb-[6px] mt-[10px] flex-row items-baseline gap-[7px]">
        {unknown ? (
          <TxtSemi className="text-[17px]" style={{ color: colour, letterSpacing: -0.4 }}>
            {verdictLabel(verdict.level)}
          </TxtSemi>
        ) : (
          <>
            <Mono className="text-[26px]" style={{ color: colour, letterSpacing: -1 }}>
              {verdict.score}
            </Mono>
            <Txt className="text-[12px] text-bone-faint">/ 100</Txt>
          </>
        )}
      </View>

      {unknown ? null : (
        <TxtSemi className="text-[13px]" style={{ color: colour }}>
          {verdictLabel(verdict.level)}
        </TxtSemi>
      )}

      <Txt className="mt-[9px] text-[12px] text-bone-secondary" style={{ lineHeight: 18 }}>
        {verdict.rationale}
      </Txt>

      {/* What the audit could not see is part of the verdict, not a footnote. */}
      {verdict.unevidencedDimensions.length > 0 ? (
        <Txt className="mt-[9px] text-[11.5px] text-bone-faint" style={{ lineHeight: 17 }}>
          No evidence for: {verdict.unevidencedDimensions.join(', ')}
        </Txt>
      ) : null}
    </View>
  );
}

/** While the audit is queued or running. */
export function AuditPending({ run }: { run: AuditRun }) {
  return (
    <View
      className="mb-4 rounded-[12px] p-[13px]"
      style={{ borderWidth: 1, borderStyle: 'dashed', borderColor: C.graphiteBright }}>
      <Mono className="text-[9px]" style={{ letterSpacing: 1.2, color: C.signal }}>
        {run.status === 'queued' ? 'AUDIT QUEUED' : 'AUDIT RUNNING'}
      </Mono>
      <Txt className="mt-[7px] text-[12.5px] text-bone-secondary" style={{ lineHeight: 19 }}>
        Your submission is being audited against rubric {run.rubricVersion}. This takes a few
        minutes. You can leave this screen — the audit keeps running and the result will be here
        when you come back.
      </Txt>
    </View>
  );
}

/** When the run reached `failed`. */
export function AuditFailed({ run }: { run: AuditRun }) {
  return (
    <View
      className="mb-4 rounded-[12px] p-[13px]"
      style={{ borderWidth: 1, borderColor: '#4A1F1E', backgroundColor: 'rgba(242,85,78,0.08)' }}>
      <Mono className="text-[9px]" style={{ letterSpacing: 1.2, color: C.alert }}>
        AUDIT FAILED
      </Mono>
      <Txt className="mt-[7px] text-[12.5px] text-bone-secondary" style={{ lineHeight: 19 }}>
        {run.errorMessage ?? 'The audit did not finish. Nothing has been scored.'}
      </Txt>
    </View>
  );
}

export function AuditReportView({ report }: { report: AuditReport }) {
  const priorities = report.actionPlan.filter((a) => a.isPriority);
  const rest = report.actionPlan.filter((a) => !a.isPriority);

  return (
    <View className="gap-4">
      <View className="flex-row items-center justify-between">
        <Mono className="text-[9px]" style={{ letterSpacing: 1.2, color: C.signal }}>
          FUNDREADY AUDIT · {report.rubricVersion}
        </Mono>
        <Mono className="text-[10px] text-bone-faint">
          DATA INTEGRITY: {report.dataIntegrityScore}
        </Mono>
      </View>

      <View className="flex-row gap-3">
        <VerdictPanel verdict={report.fundability} title="Fundability" />
        <VerdictPanel verdict={report.saleability} title="Saleability" />
      </View>

      {/* Contradictions the audit found across what was submitted. */}
      {report.findings.length > 0 ? (
        <View className="rounded-[12px] border border-graphite bg-carbon-low p-[14px]">
          <Eyebrow>What does not add up</Eyebrow>
          {report.findings.map((finding, index) => (
            <View key={`${finding.code}-${index}`} className="mt-[10px]">
              <View className="mb-[4px] flex-row items-center gap-2">
                <View
                  className="h-[5px] w-[5px] rounded-full"
                  style={{ backgroundColor: finding.severity === 'high' ? C.alert : C.flag }}
                />
                <Mono className="text-[9.5px] text-bone-faint" style={{ letterSpacing: 0.8 }}>
                  {finding.severity.toUpperCase()}
                </Mono>
              </View>
              <Txt className="text-[12.5px] text-bone-secondary" style={{ lineHeight: 19 }}>
                {finding.message}
              </Txt>
              {finding.fields.length > 0 ? (
                <Mono className="mt-[3px] text-[10px] text-bone-faint">
                  {finding.fields.join(' · ')}
                </Mono>
              ) : null}
            </View>
          ))}
        </View>
      ) : null}

      {report.actionPlan.length > 0 ? (
        <View className="rounded-[12px] border border-graphite bg-carbon-low p-[14px]">
          <Eyebrow>What to do next</Eyebrow>
          {[...priorities, ...rest].map((item, index) => (
            <View key={`${item.dimension}-${index}`} className="mt-[11px] flex-row gap-[9px]">
              <Mono
                className="text-[10px]"
                style={{ color: item.isPriority ? C.flag : C.boneFaint, lineHeight: 18 }}>
                {item.isPriority ? '!' : '·'}
              </Mono>
              <View className="flex-1">
                <Txt className="text-[12.5px] text-bone" style={{ lineHeight: 19 }}>
                  {item.action}
                </Txt>
                <Mono className="mt-[3px] text-[10px] text-bone-faint">
                  {item.dimension}
                  {item.dimensionScore === null ? '' : ` · ${item.dimensionScore}/100`}
                </Mono>
              </View>
            </View>
          ))}
        </View>
      ) : null}
    </View>
  );
}
