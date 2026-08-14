"use client";

import { useId, useState } from "react";

export function FileField({
  label,
  hint,
  accept,
  onFile,
  disabled,
}: {
  label: string;
  hint?: string;
  accept?: string;
  onFile: (file: File) => void | Promise<void>;
  disabled?: boolean;
}) {
  const id = useId();
  const [name, setName] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  return (
    <div>
      <label htmlFor={id} className="mb-1.5 block text-[12px] font-semibold text-cream">
        {label}
      </label>
      <input
        id={id}
        type="file"
        accept={accept}
        disabled={disabled || busy}
        className="block min-h-11 w-full text-sm text-mist file:mr-3 file:rounded-[10px] file:border-0 file:bg-rail-active file:px-3 file:py-2 file:text-sm file:font-semibold file:text-cream file:ring-1 file:ring-black/5 file:dark:ring-white/10"
        onChange={async (e) => {
          const file = e.target.files?.[0];
          if (!file) return;
          setName(file.name);
          setBusy(true);
          try {
            await onFile(file);
          } finally {
            setBusy(false);
            e.target.value = "";
          }
        }}
      />
      {name ? <p className="mt-1 text-xs text-cream">{busy ? `Uploading ${name}…` : name}</p> : null}
      {hint ? <p className="mt-1 text-xs text-mist">{hint}</p> : null}
    </div>
  );
}
