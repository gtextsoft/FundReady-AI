"use client";

import { useEffect, useRef } from "react";
import { Button } from "@/components/ui/button";

export function ConfirmDialog({
  open,
  title,
  body,
  confirmLabel = "Confirm",
  danger = false,
  busy = false,
  onConfirm,
  onClose,
}: {
  open: boolean;
  title: string;
  body: string;
  confirmLabel?: string;
  danger?: boolean;
  busy?: boolean;
  onConfirm: () => void | Promise<void>;
  onClose: () => void;
}) {
  const dialogRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const prev = document.activeElement as HTMLElement | null;
    const node = dialogRef.current;
    node?.querySelector<HTMLElement>("button")?.focus();
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    document.addEventListener("keydown", onKey);
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = "";
      prev?.focus();
    };
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <button type="button" className="absolute inset-0 bg-navy/50" aria-label="Dismiss" onClick={onClose} />
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="confirm-title"
        className="relative w-full max-w-md rounded-[22px] bg-rail-active p-6 shadow-[0_16px_50px_rgba(16,28,44,0.18)] ring-1 ring-black/5 dark:ring-white/10"
      >
        <h2 id="confirm-title" className="text-xl font-semibold tracking-[-0.02em] text-cream">
          {title}
        </h2>
        <p className="mt-2 text-sm text-mist">{body}</p>
        <div className="mt-6 flex justify-end gap-2">
          <Button type="button" variant="ghost" onClick={onClose} disabled={busy}>
            Cancel
          </Button>
          <Button type="button" variant={danger ? "danger" : "primary"} loading={busy} onClick={() => void onConfirm()}>
            {confirmLabel}
          </Button>
        </div>
      </div>
    </div>
  );
}
