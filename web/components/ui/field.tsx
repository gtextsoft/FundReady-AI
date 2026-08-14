"use client";

import { cn } from "@/lib/utils";
import { Eye, EyeOff } from "lucide-react";
import { useId, useState, type InputHTMLAttributes, type TextareaHTMLAttributes, type SelectHTMLAttributes } from "react";

export function Field({
  label,
  hint,
  error,
  className,
  type,
  id,
  ...props
}: InputHTMLAttributes<HTMLInputElement> & {
  label: string;
  hint?: string;
  error?: string | null;
}) {
  const generated = useId();
  const inputId = id ?? generated;
  const hintId = `${inputId}-hint`;
  const errorId = `${inputId}-error`;
  const [revealed, setRevealed] = useState(false);
  const isPassword = type === "password";
  const inputType = isPassword ? (revealed ? "text" : "password") : type;

  return (
    <div className={cn("block", className)}>
      <label htmlFor={inputId} className="mb-1.5 block text-[12px] font-semibold tracking-normal text-cream">
        {label}
      </label>
      <div className="relative">
        <input
          id={inputId}
          type={inputType}
          aria-invalid={error ? true : undefined}
          aria-describedby={error ? errorId : hint ? hintId : undefined}
          className={cn(
            "min-h-11 w-full rounded-[10px] bg-white px-3.5 py-3 text-[16px] text-cream ring-1 outline-none placeholder:text-mist-2 focus:ring-2 focus:ring-brand sm:text-[13px] dark:bg-surface-2",
            isPassword && "pr-11",
            error ? "ring-fail" : "ring-black/5 dark:ring-white/10",
          )}
          {...props}
        />
        {isPassword ? (
          <button
            type="button"
            onClick={() => setRevealed((v) => !v)}
            className="absolute right-2 top-1/2 flex h-11 w-11 -translate-y-1/2 items-center justify-center text-mist hover:text-cream"
            aria-label={revealed ? "Hide password" : "Show password"}
            aria-pressed={revealed}
          >
            {revealed ? <EyeOff size={18} /> : <Eye size={18} />}
          </button>
        ) : null}
      </div>
      {error ? (
        <p id={errorId} role="alert" className="mt-1 text-xs text-fail">
          {error}
        </p>
      ) : null}
      {hint && !error ? (
        <p id={hintId} className="mt-1 text-xs text-mist">
          {hint}
        </p>
      ) : null}
    </div>
  );
}

export function TextArea({
  label,
  hint,
  error,
  className,
  id,
  ...props
}: TextareaHTMLAttributes<HTMLTextAreaElement> & { label: string; hint?: string; error?: string | null }) {
  const generated = useId();
  const inputId = id ?? generated;
  const hintId = `${inputId}-hint`;
  const errorId = `${inputId}-error`;
  return (
    <div className={cn("block", className)}>
      <label htmlFor={inputId} className="mb-1.5 block text-[12px] font-semibold tracking-normal text-cream">
        {label}
      </label>
      <textarea
        id={inputId}
        aria-invalid={error ? true : undefined}
        aria-describedby={error ? errorId : hint ? hintId : undefined}
        className={cn(
          "min-h-28 w-full rounded-[10px] bg-white px-3.5 py-3.5 text-[16px] text-cream ring-1 outline-none placeholder:text-mist-2 focus:ring-2 focus:ring-brand sm:text-[13px] dark:bg-surface-2",
          error ? "ring-fail" : "ring-black/5 dark:ring-white/10",
        )}
        {...props}
      />
      {error ? (
        <p id={errorId} role="alert" className="mt-1 text-xs text-fail">
          {error}
        </p>
      ) : null}
      {hint && !error ? (
        <p id={hintId} className="mt-1 text-xs text-mist">
          {hint}
        </p>
      ) : null}
    </div>
  );
}

export function Select({
  label,
  children,
  className,
  id,
  error,
  ...props
}: SelectHTMLAttributes<HTMLSelectElement> & { label: string; error?: string | null }) {
  const generated = useId();
  const inputId = id ?? generated;
  const errorId = `${inputId}-error`;
  return (
    <div className={cn("block", className)}>
      <label htmlFor={inputId} className="mb-1.5 block text-[12px] font-semibold tracking-normal text-cream">
        {label}
      </label>
      <select
        id={inputId}
        aria-invalid={error ? true : undefined}
        aria-describedby={error ? errorId : undefined}
        className={cn(
          "min-h-11 w-full rounded-[10px] bg-white px-3.5 py-3 text-[16px] text-cream ring-1 outline-none focus:ring-2 focus:ring-brand sm:text-[13px] dark:bg-surface-2",
          error ? "ring-fail" : "ring-black/5 dark:ring-white/10",
        )}
        {...props}
      >
        {children}
      </select>
      {error ? (
        <p id={errorId} role="alert" className="mt-1 text-xs text-fail">
          {error}
        </p>
      ) : null}
    </div>
  );
}
