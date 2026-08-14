import Link from "next/link";
import { cn } from "@/lib/utils";
import type { ButtonHTMLAttributes } from "react";

const variants = {
  primary: "bg-brand text-brand-ink hover:bg-brand-hover disabled:opacity-50",
  ghost:
    "bg-rail-active text-cream ring-1 ring-black/5 hover:ring-brand/30 disabled:opacity-50 dark:ring-white/10",
  danger: "bg-fail text-white hover:opacity-90 disabled:opacity-50",
  quiet: "text-mist hover:text-cream disabled:opacity-50",
};

const sizes = {
  sm: "px-3 py-2 text-xs min-h-11",
  md: "px-5 py-3.5 text-sm min-h-11",
  lg: "px-6 py-4 text-sm min-h-12",
};

export function Button({
  variant = "primary",
  size = "md",
  loading = false,
  href,
  className,
  children,
  disabled,
  type = "button",
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: keyof typeof variants;
  size?: keyof typeof sizes;
  loading?: boolean;
  href?: string;
}) {
  const classes = cn(
    "inline-flex cursor-pointer items-center justify-center gap-2 rounded-[10px] font-semibold transition-colors duration-200 disabled:cursor-not-allowed",
    variants[variant],
    sizes[size],
    className,
  );

  if (href) {
    return (
      <Link href={href} className={classes} aria-disabled={loading || disabled} tabIndex={loading || disabled ? -1 : undefined}>
        {loading ? "Working…" : children}
      </Link>
    );
  }

  return (
    <button type={type} className={classes} disabled={disabled || loading} aria-busy={loading} {...props}>
      {loading ? "Working…" : children}
    </button>
  );
}
