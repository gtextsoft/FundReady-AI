import { create } from 'zustand';
import { api, type Role, type Session } from '@/api';
import { checkFounderEmail } from '@/domain/email';
import type { FounderAccount, InvestorAccount } from '@/domain/types';
import { storage } from '@/lib/storage';

const KEY = 'saci.fundme.session';

type Status = 'loading' | 'signedOut' | 'signedIn';

type SessionState = {
  status: Status;
  session: Session | null;
  /** Fixed at sign-up. A founder never sees the investor side, or vice versa. */
  role: Role;
  founderAccount: FounderAccount | null;
  investorAccount: InvestorAccount | null;
  error: string | null;
  busy: boolean;

  restore(): Promise<void>;
  signIn(email: string, password: string): Promise<Session | null>;
  signUp(email: string, password: string, role: Role): Promise<Session | null>;
  /** Sign in through the company's own identity provider. */
  signInWithSso(domain: string, role: Role): Promise<Session | null>;
  signOut(): Promise<void>;
  clearError(): void;

  refreshAccount(): Promise<void>;
  setFounderAccount(account: FounderAccount): void;
  setInvestorAccount(account: InvestorAccount): void;
};

/**
 * Note: there is deliberately no `can()` helper on this store. A method that
 * reads state internally looks pure to the React Compiler, which then caches
 * its result and never recomputes it when the account changes — locked tiles
 * stay locked after verification clears. Screens call `gate(account, …)` from
 * `@/domain/access` instead, so the account is a visible dependency.
 */

export const useSession = create<SessionState>((set, get) => ({
  status: 'loading',
  session: null,
  role: 'founder',
  founderAccount: null,
  investorAccount: null,
  error: null,
  busy: false,

  async restore() {
    const raw = await storage.get(KEY);
    if (!raw) {
      set({ status: 'signedOut', session: null });
      return;
    }
    try {
      const session = JSON.parse(raw) as Session;
      set({ status: 'signedIn', session, role: session.role });
      await get().refreshAccount();
    } catch {
      await storage.remove(KEY);
      set({ status: 'signedOut', session: null });
    }
  },

  async signIn(email, password) {
    set({ busy: true, error: null });
    try {
      const session = await api.signIn({ email, password });
      await storage.set(KEY, JSON.stringify(session));
      set({ status: 'signedIn', session, role: session.role, busy: false });
      await get().refreshAccount();
      return session;
    } catch {
      set({ busy: false, error: 'We could not sign you in. Check your email and password.' });
      return null;
    }
  },

  async signUp(email, password, role) {
    // Founders must sign up on a company domain. Checked here as well as on
    // the server so the answer is instant and costs no round trip.
    if (role === 'founder') {
      const verdict = checkFounderEmail(email);
      if (!verdict.ok) {
        set({ error: verdict.message });
        return null;
      }
    }

    set({ busy: true, error: null });
    try {
      const session = await api.signUp({ email, password, role });
      await storage.set(KEY, JSON.stringify(session));
      set({ status: 'signedIn', session, role: session.role, busy: false });
      await get().refreshAccount();
      return session;
    } catch (e) {
      const personal = e instanceof Error && e.message === 'personal_email_domain';
      set({
        busy: false,
        error: personal
          ? 'Founder accounts need a company email address, not a personal one.'
          : 'We could not create your account. Try again.',
      });
      return null;
    }
  },

  async signInWithSso(domain, role) {
    set({ busy: true, error: null });
    try {
      const session = await api.signInWithSso(domain, role);
      await storage.set(KEY, JSON.stringify(session));
      set({ status: 'signedIn', session, role: session.role, busy: false });
      await get().refreshAccount();
      return session;
    } catch {
      set({ busy: false, error: `We could not reach the single sign-on service for ${domain}.` });
      return null;
    }
  },

  async signOut() {
    await api.signOut();
    await storage.remove(KEY);
    set({
      status: 'signedOut',
      session: null,
      role: 'founder',
      founderAccount: null,
      investorAccount: null,
      error: null,
    });
  },

  clearError() {
    set({ error: null });
  },

  async refreshAccount() {
    if (get().role === 'founder') {
      set({ founderAccount: await api.getFounderAccount() });
    } else {
      set({ investorAccount: await api.getInvestorAccount() });
    }
  },

  setFounderAccount(founderAccount) {
    set({ founderAccount });
  },

  setInvestorAccount(investorAccount) {
    set({ investorAccount });
  },
}));
