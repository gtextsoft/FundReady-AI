"use client";

import { useEffect } from "react";
import { setUnauthorizedHandler } from "@/lib/api";
import { useSession } from "@/stores/session";

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const restore = useSession((s) => s.restore);
  useEffect(() => {
    setUnauthorizedHandler(() => {
      const { status, signOut } = useSession.getState();
      if (status === "signedIn") void signOut();
    });
    void restore();
    return () => setUnauthorizedHandler(null);
  }, [restore]);
  return <>{children}</>;
}
