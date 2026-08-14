"use client";

import { useCallback, useEffect, useState } from "react";
import { api, type ProfileResponse } from "@/lib/api";
import { ApiFailure } from "@/lib/api/errors";

export function useStartup(enabled = true) {
  const [enabledState, setEnabledState] = useState(enabled);
  const [profile, setProfile] = useState<ProfileResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(enabled);

  if (enabled !== enabledState) {
    setEnabledState(enabled);
    setProfile(null);
    setError(null);
    setLoading(enabled);
  }

  const reload = useCallback(async () => {
    if (!enabled) {
      setLoading(false);
      return;
    }
    setLoading(true);
    try {
      const p = await api.getProfile();
      setProfile(p);
      setError(null);
    } catch (err) {
      if (err instanceof ApiFailure && err.code === "not_found") {
        setProfile(null);
        setError(null);
      } else {
        setError(err instanceof ApiFailure ? err.message : "Could not load the profile.");
      }
    } finally {
      setLoading(false);
    }
  }, [enabled]);

  useEffect(() => {
    void reload();
  }, [reload]);

  return { profile, error, loading, reload, setProfile };
}
