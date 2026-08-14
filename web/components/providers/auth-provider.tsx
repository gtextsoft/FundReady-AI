"use client";

import { useEffect } from "react";
import { useSession } from "@/stores/session";

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const restore = useSession((s) => s.restore);
  useEffect(() => {
    void restore();
  }, [restore]);
  return <>{children}</>;
}
