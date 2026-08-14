import { DualAxisStamp } from "@/components/brand/dual-axis-stamp";
import type { AuditReport } from "@/lib/api";
import { Badge } from "@/components/ui/states";

export function PaperReport({ report }: { report: AuditReport }) {
  return (
    <article className="paper-grain border border-line px-8 py-10 text-paper-ink shadow-[0_18px_50px_rgb(39_58_48_/_0.13)] md:px-12">
      <p className="text-[9px] font-extrabold uppercase tracking-[0.18em] text-brass">
        FundReady AI · rubric {report.rubric_version} · integrity {String(report.data_integrity_score)}
      </p>
      <h2 className="mt-3 font-display text-4xl">Audit report</h2>
      <div className="mt-8 flex flex-col items-start gap-8 md:flex-row md:items-center md:justify-between">
        <DualAxisStamp fundability={report.fundability} saleability={report.saleability} />
        <div className="max-w-md space-y-4 text-sm leading-relaxed">
          <p>
            <span className="font-medium">Fundability.</span> {report.fundability.rationale}
          </p>
          <p>
            <span className="font-medium">Saleability.</span> {report.saleability.rationale}
          </p>
        </div>
      </div>
      {report.findings.length ? (
        <section className="mt-10 border-t border-line pt-6">
          <h3 className="font-display text-2xl">Findings</h3>
          <ul className="mt-4 space-y-3">
            {report.findings.map((f) => (
              <li key={f.code} className="text-sm">
                <Badge tone={f.severity === "certain" ? "fail" : "hold"}>{f.severity}</Badge>
                <span className="ml-2">{f.message}</span>
                {f.detail ? <span className="mt-1 block font-mono text-xs text-mist">{f.detail}</span> : null}
              </li>
            ))}
          </ul>
        </section>
      ) : null}
      {report.action_plan.length ? (
        <section className="mt-10 border-t border-line pt-6">
          <h3 className="font-display text-2xl">Action plan</h3>
          <ol className="mt-4 space-y-3">
            {report.action_plan.map((a, i) => (
              <li key={`${a.dimension}-${i}`} className="text-sm">
                <span className="font-mono text-xs uppercase tracking-wider text-mist">
                  {a.dimension.replace(/_/g, " ")}
                  {a.is_priority ? " · priority" : ""}
                </span>
                <p className="mt-1">{a.action}</p>
              </li>
            ))}
          </ol>
        </section>
      ) : null}
    </article>
  );
}
