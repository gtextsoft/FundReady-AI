import { Mark } from "@/components/brand/mark";

export function AssessmentLoader({ message }: { message: string }) {
  return (
    <div className="flex flex-col items-center" aria-busy="true" aria-live="polite">
      <span className="sr-only">Scoring in progress. {message}</span>
      <div className="relative grid size-[7.5rem] place-items-center">
        <span className="absolute inset-0 rounded-full bg-brand/6 ring-1 ring-brand/10" />
        <span
          className="absolute inset-0 rounded-full border-2 border-transparent border-t-brand border-r-brand/35"
          style={{ animation: "fr-spin 2.4s linear infinite" }}
        />
        <span
          className="absolute inset-2.5 rounded-full border-2 border-transparent border-b-accent border-l-accent/60"
          style={{ animation: "fr-spin-rev 3.6s linear infinite" }}
        />
        <span className="grid place-items-center" style={{ animation: "fr-breathe 2s ease-in-out infinite" }}>
          <Mark size={48} />
        </span>
      </div>
      <p className="mt-6 text-[22px] font-extrabold tracking-[-0.04em] text-cream">
        Fundready
        <span className="text-brass">.</span>
      </p>
      <h1 className="mt-8 font-display text-4xl text-cream">Assessment in motion.</h1>
      <p className="mt-4 max-w-md text-sm text-mist">{message}</p>
      <div className="mt-8 h-1 w-52 overflow-hidden rounded-full bg-line" aria-hidden>
        <div
          className="h-full w-1/3 rounded-full bg-brand"
          style={{ animation: "fr-sweep 1.35s ease-in-out infinite" }}
        />
      </div>
      <div className="mt-4 flex gap-1.5" aria-hidden>
        {[0, 1, 2].map((i) => (
          <span
            key={i}
            className="size-1.5 rounded-full bg-brand"
            style={{ animation: "fr-dots 1.2s ease-in-out infinite", animationDelay: `${i * 0.18}s` }}
          />
        ))}
      </div>
    </div>
  );
}
