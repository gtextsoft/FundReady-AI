import Link from "next/link";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Panel } from "@/components/ui/panel";

export function EmptyState({
  title,
  body,
  action,
}: {
  title: string;
  body: string;
  action?: React.ReactNode;
}) {
  return (
    <Panel className="px-8 py-14 text-center">
      <p className="text-xl font-semibold tracking-[-0.02em] text-cream">{title}</p>
      <p className="mx-auto mt-2 max-w-md text-sm text-mist">{body}</p>
      {action ? <div className="mt-6">{action}</div> : null}
    </Panel>
  );
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div
      className="rounded-[22px] bg-fail/10 px-6 py-8 ring-1 ring-fail/20"
      role="alert"
    >
      <p className="text-sm font-semibold text-fail">Could not load</p>
      <p className="mt-1 text-sm text-mist">{message}</p>
      {onRetry ? (
        <Button type="button" variant="ghost" size="sm" className="mt-4" onClick={onRetry}>
          Try again
        </Button>
      ) : null}
    </div>
  );
}

export function LockedCard({
  title,
  body,
  cta,
  href,
}: {
  title: string;
  body: string;
  cta: string;
  href: string;
}) {
  return (
    <Panel className="bg-rail-promo">
      <p className="text-[10px] font-extrabold tracking-[0.16em] text-hold uppercase">Locked</p>
      <p className="mt-2 text-lg font-semibold tracking-[-0.02em] text-cream">{title}</p>
      <p className="mt-1 text-sm text-mist">{body}</p>
      <Link
        href={href}
        className="mt-4 inline-flex min-h-11 items-center text-sm font-semibold text-brand hover:text-brand-hover"
      >
        {cta} →
      </Link>
    </Panel>
  );
}

export function Badge({
  children,
  tone = "mist",
}: {
  children: React.ReactNode;
  tone?: "mist" | "pass" | "hold" | "fail" | "brass" | "signal";
}) {
  const map = {
    mist: "bg-surface-3 text-mist",
    pass: "bg-pass/10 text-pass",
    hold: "bg-hold/10 text-hold",
    fail: "bg-fail/10 text-fail",
    brass: "bg-brand/10 text-brand",
    signal: "bg-brand/10 text-signal",
  };
  return (
    <span className={cn("inline-flex rounded-full px-2.5 py-0.5 text-[11px] font-semibold", map[tone])}>
      {children}
    </span>
  );
}
