import { cn } from "@/lib/utils";

export function Skeleton({ className }: { className?: string }) {
  return <div className={cn("animate-pulse rounded-[12px] bg-surface-2", className)} />;
}

export function PageSkeleton({ rows = 3 }: { rows?: number }) {
  return (
    <div className="space-y-4" aria-busy="true" aria-live="polite">
      <span className="sr-only">Loading</span>
      <Skeleton className="h-8 w-48" />
      <Skeleton className="h-4 w-80 max-w-full" />
      {Array.from({ length: rows }).map((_, i) => (
        <Skeleton key={i} className="h-24 w-full rounded-[22px]" />
      ))}
    </div>
  );
}
