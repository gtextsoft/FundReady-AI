"use client";

import { create } from "zustand";
import {
  login as apiLogin,
  logout as apiLogout,
  restoreSession,
  verifyMfaLogin,
  type Session,
} from "@/lib/api";
import { ApiFailure, MfaRequired } from "@/lib/api/errors";

type Status = "loading" | "signedOut" | "signedIn";

type SessionStore = {
  status: Status;
  session: Session | null;
  mfaToken: string | null;
  error: string | null;
  busy: boolean;
  restore: () => Promise<void>;
  signIn: (email: string, password: string) => Promise<Session | null>;
  verifyMfa: (code: string) => Promise<Session | null>;
  refresh: () => Promise<void>;
  signOut: () => Promise<void>;
  clearError: () => void;
};

export const useSession = create<SessionStore>((set, get) => ({
  status: "loading",
  session: null,
  mfaToken: null,
  error: null,
  busy: false,

  restore: async () => {
    const session = await restoreSession();
    set({ status: session ? "signedIn" : "signedOut", session, mfaToken: null });
  },

  signIn: async (email, password) => {
    set({ busy: true, error: null, mfaToken: null });
    try {
      const session = await apiLogin(email, password);
      set({ status: "signedIn", session, busy: false });
      return session;
    } catch (err) {
      if (err instanceof MfaRequired) {
        set({ busy: false, mfaToken: err.mfaToken, error: null });
        return null;
      }
      const message = err instanceof ApiFailure ? err.message : "Could not sign in.";
      set({ busy: false, error: message });
      return null;
    }
  },

  verifyMfa: async (code) => {
    const token = get().mfaToken;
    if (!token) {
      set({ error: "The verification challenge expired. Sign in again." });
      return null;
    }
    set({ busy: true, error: null });
    try {
      const session = await verifyMfaLogin(token, code);
      set({ status: "signedIn", session, busy: false, mfaToken: null });
      return session;
    } catch (err) {
      const message = err instanceof ApiFailure ? err.message : "That code was not accepted.";
      set({ busy: false, error: message });
      return null;
    }
  },

  refresh: async () => {
    const session = await restoreSession();
    if (session) set({ session, status: "signedIn" });
  },

  signOut: async () => {
    set({ status: "signedOut", session: null, mfaToken: null });
    await apiLogout();
  },

  clearError: () => set({ error: null }),
}));
