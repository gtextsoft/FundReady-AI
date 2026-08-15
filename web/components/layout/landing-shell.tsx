import { LandingFooter } from "@/components/layout/landing-footer";
import { LandingNav } from "@/components/layout/landing-nav";

export function LandingShell({
  eyebrow,
  title,
  children,
}: {
  eyebrow: string;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div id="main" tabIndex={-1} className="relative min-h-dvh bg-bg text-cream">
      <LandingNav />
      <article className="mx-auto max-w-[800px] px-5 pb-20 pt-12 lg:px-7">
        <p className="text-[11px] font-extrabold tracking-[0.2em] text-brass">{eyebrow}</p>
        <h1 className="mt-4 font-display text-[38px] leading-tight tracking-[-0.03em] lg:text-[52px]">
          {title}
        </h1>
        <div className="mt-10 space-y-6 text-sm leading-relaxed text-mist">{children}</div>
      </article>
      <LandingFooter />
    </div>
  );
}
