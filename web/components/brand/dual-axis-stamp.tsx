import { cn } from "@/lib/utils";

function band(level: string | undefined, score: number | null) {
  const n = (level ?? "").toLowerCase();
  if (n === "ready" || n === "fundable" || n === "saleable") return "pass";
  if (n === "provisional") return "signal";
  if (n === "not_yet") return "hold";
  if (score == null || n === "insufficient_data") return "mist";
  return "mist";
}

function label(level: string | undefined) {
  const known: Record<string, string> = {
    ready: "Ready",
    fundable: "Fundable",
    saleable: "Saleable",
    not_yet: "Not yet",
    provisional: "Provisional",
    insufficient_data: "Thin data",
  };
  if (!level) return "—";
  return known[level] ?? level.replace(/_/g, " ");
}

function Arc({
  cx,
  cy,
  r,
  progress,
  color,
}: {
  cx: number;
  cy: number;
  r: number;
  progress: number;
  color: string;
}) {
  const p = Math.max(0, Math.min(1, progress));
  const start = -Math.PI * 0.75;
  const end = start + Math.PI * 1.5 * p;
  const large = p > 2 / 3 ? 1 : 0;
  const x1 = cx + r * Math.cos(start);
  const y1 = cy + r * Math.sin(start);
  const x2 = cx + r * Math.cos(end);
  const y2 = cy + r * Math.sin(end);
  return (
    <path
      d={`M ${x1} ${y1} A ${r} ${r} 0 ${large} 1 ${x2} ${y2}`}
      fill="none"
      stroke={color}
      strokeWidth="10"
      strokeLinecap="butt"
    />
  );
}

export function DualAxisStamp({
  fundability,
  saleability,
  size = 168,
  className,
}: {
  fundability: { level?: string; score: number | null };
  saleability: { level?: string; score: number | null };
  size?: number;
  className?: string;
}) {
  const sBand = band(saleability.level, saleability.score);
  const fProg = fundability.score == null ? 0 : fundability.score / 100;
  const sProg = saleability.score == null ? 0 : saleability.score / 100;
  const fScore = fundability.score == null ? "—" : String(Math.round(fundability.score));
  const sScore = saleability.score == null ? "—" : String(Math.round(saleability.score));
  const summary = `Fundability ${fScore} of 100, ${label(fundability.level)}. Saleability ${sScore} of 100, ${label(saleability.level)}.`;

  return (
    <div className={cn("relative inline-flex flex-col items-center", className)}>
      <p className="sr-only">{summary}</p>
      <svg width={size} height={size} viewBox="0 0 200 200" aria-hidden>
        <circle cx="100" cy="100" r="82" fill="none" stroke="var(--border)" strokeWidth="10" />
        <circle cx="100" cy="100" r="56" fill="none" stroke="var(--surface-2)" strokeWidth="10" />
        <Arc cx={100} cy={100} r={82} progress={fProg} color="var(--brand)" />
        <Arc cx={100} cy={100} r={56} progress={sProg} color="var(--accent)" />
        <text
          x="100"
          y="96"
          textAnchor="middle"
          fill="var(--paper-ink)"
          fontFamily="var(--font-display), Georgia, serif"
          fontSize="40"
        >
          {fScore}
        </text>
        <text
          x="100"
          y="118"
          textAnchor="middle"
          fill="var(--text-faint)"
          fontFamily="var(--font-sans), sans-serif"
          fontSize="11"
          letterSpacing="1.5"
        >
          / 100
        </text>
      </svg>
      <div className="mt-1 flex gap-4 text-[11px] uppercase tracking-[0.16em] text-mist">
        <span>
          Fund <span className="text-cream">{label(fundability.level)}</span>
        </span>
        <span>
          Sale <span className={sBand === "pass" ? "text-pass" : sBand === "hold" ? "text-hold" : "text-mist"}>{label(saleability.level)}</span>
          {saleability.score != null ? (
            <span className="ml-1 font-mono text-cream">{Math.round(saleability.score)}</span>
          ) : null}
        </span>
      </div>
    </div>
  );
}
