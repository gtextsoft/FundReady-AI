"use client";

import { useEffect, useState } from "react";
import { Toaster } from "sonner";

export function ThemedToaster() {
  const [dark, setDark] = useState(false);

  useEffect(() => {
    const sync = () => setDark(document.documentElement.classList.contains("dark"));
    sync();
    const obs = new MutationObserver(sync);
    obs.observe(document.documentElement, { attributes: true, attributeFilter: ["class"] });
    return () => obs.disconnect();
  }, []);

  return (
    <Toaster
      theme={dark ? "dark" : "light"}
      toastOptions={{
        style: {
          background: "var(--surface)",
          border: "1px solid var(--border)",
          color: "var(--text)",
        },
      }}
    />
  );
}
