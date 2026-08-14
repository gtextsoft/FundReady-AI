import { cn } from "@/lib/utils";

export const PANEL_SHADOW =
  "shadow-[0_1px_2px_rgba(16,28,44,0.06),0_8px_24px_rgba(16,28,44,0.05)] dark:shadow-none";

export const PANEL_RING = "ring-1 ring-black/5 dark:ring-white/10";

export function Panel({
  className,
  children,
  as: Tag = "div",
}: {
  className?: string;
  children: React.ReactNode;
  as?: "div" | "section" | "aside" | "article";
}) {
  return (
    <Tag className={cn("rounded-[22px] bg-rail-active p-5", PANEL_SHADOW, PANEL_RING, className)}>
      {children}
    </Tag>
  );
}

export function PanelList({
  className,
  children,
  ...props
}: {
  className?: string;
  children: React.ReactNode;
} & React.HTMLAttributes<HTMLUListElement>) {
  return (
    <ul
      className={cn("grid gap-1 rounded-[22px] bg-rail-active p-2", PANEL_SHADOW, PANEL_RING, className)}
      {...props}
    >
      {children}
    </ul>
  );
}

export function PanelRow({
  className,
  children,
  active = false,
  as: Tag = "li",
}: {
  className?: string;
  children: React.ReactNode;
  active?: boolean;
  as?: "li" | "div";
}) {
  return (
    <Tag
      className={cn(
        "rounded-[12px] px-4 py-3.5 transition-colors duration-150",
        active
          ? "bg-white shadow-[0_1px_2px_rgba(16,28,44,0.07),0_6px_16px_rgba(16,28,44,0.06)] dark:bg-surface-3 dark:shadow-none"
          : "hover:bg-rail-hover",
        className,
      )}
    >
      {children}
    </Tag>
  );
}

export function SectionLabel({
  className,
  children,
}: {
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <p className={cn("text-[10px] font-extrabold tracking-[0.16em] text-text-faint uppercase", className)}>
      {children}
    </p>
  );
}

export function MetaList({
  className,
  children,
}: {
  className?: string;
  children: React.ReactNode;
}) {
  return <dl className={cn("divide-y divide-black/5 dark:divide-white/10", className)}>{children}</dl>;
}

export function MetaRow({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex items-start justify-between gap-4 py-3 text-sm first:pt-0 last:pb-0">
      <dt className="text-mist">{label}</dt>
      <dd className="text-right text-cream">{children}</dd>
    </div>
  );
}
