import { cn } from "@/lib/utils";

export function Mark({ size = 30, className }: { size?: number; className?: string }) {
  return (
    <span
      className={cn(
        "inline-grid place-items-center rounded-full bg-brass font-display text-[0.72em] font-normal italic text-white",
        className,
      )}
      style={{ width: size, height: size, fontSize: size * 0.55 }}
      aria-hidden
    >
      F
    </span>
  );
}

export function BrandMark({
  size = 30,
  inverse = false,
}: {
  size?: number;
  inverse?: boolean;
}) {
  return (
    <span className={cn("inline-flex items-center gap-2", inverse ? "text-white" : "text-cream")}>
      <Mark size={size} className={inverse ? "bg-lime text-navy" : undefined} />
      <span className="text-[22px] font-extrabold tracking-[-0.04em]">
        Fundready
        <span className={inverse ? "text-lime" : "text-brass"}>.</span>
      </span>
    </span>
  );
}
