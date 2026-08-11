import { create } from 'zustand';
import { api, ApiFailure, type Role, type Session } from '@/api';
import { MfaRequired } from '@/api/http';
import { checkFounderEmail } from '@/domain/email';
import type { FounderAccount, InvestorAccount } from '@/domain/types';
import { storage } from '@/lib/storage';

const KEY = 'fundready.session';

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
  /**
   * Set when a password was accepted but a second factor is outstanding. It
   * grants nothing on its own and expires in five minutes; the code screen
   * exchanges it for a real session.
   */
  mfaToken: string | null;

  restore(): Promise<void>;
  /** Finish an `mfa_required` login with an authenticator or recovery code. */
  verifyMfa(code: string): Promise<Session | null>;
  clearMfa(): void;
  signIn(email: string, password: string): Promise<Session | null>;
  signUp(registration: {
    email: string;
    password: string;
    role: Role;
    firstName: string;
    lastName: string;
  }): Promise<Session | null>;
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
  mfaToken: null,

  async restore() {
    const raw = await storage.get(KEY);
    if (!raw) {
      set({ status: 'signedOut', session: null });
      return;
    }
    let session: Session;
    try {
      session = JSON.parse(raw) as Session;
    } catch {
      await storage.remove(KEY);
      set({ status: 'signedOut', session: null });
      return;
    }

    set({ status: 'signedIn', session, role: session.role });
    try {
      await get().refreshAccount();
    } catch (e) {
      // The stored session is only as good as the tokens behind it. If the
      // server rejects them, sign out rather than showing a shell of an app;
      // a transport failure keeps the session so a flaky network is survivable.
      if (e instanceof ApiFailure && (e.code === 'unauthorized' || e.code === 'forbidden')) {
        await storage.remove(KEY);
        set({ status: 'signedOut', session: null });
      }
    }
  },

  async signIn(email, password) {
    set({ busy: true, error: null, mfaToken: null });
    try {
      const session = await api.signIn({ email, password });
      await storage.set(KEY, JSON.stringify(session));
      set({ status: 'signedIn', session, role: session.role, busy: false });
      await get().refreshAccount();
      return session;
    } catch (e) {
      // Not a failure: the password was right and a code is outstanding.
      if (e instanceof MfaRequired) {
        set({ busy: false, mfaToken: e.mfaToken });
        return null;
      }
      set({ busy: false, error: 'We could not sign you in. Check your email and password.' });
      return null;
    }
  },

  async verifyMfa(code) {
    const mfaToken = get().mfaToken;
    if (!mfaToken) {
      set({ error: 'That sign-in attempt expired. Please start again.' });
      return null;
    }

    set({ busy: true, error: null });
    try {
      const session = await api.verifyMfa(mfaToken, code);
      await storage.set(KEY, JSON.stringify(session));
      set({ status: 'signedIn', session, role: session.role, busy: false, mfaToken: null });
      await get().refreshAccount();
      return session;
    } catch {
      // One message for a wrong code, a replayed code and an expired
      // challenge alike — the server does not distinguish them either.
      set({ busy: false, error: 'That code was not accepted. Try the current one.' });
      return null;
    }
  },

  clearMfa() {
    set({ mfaToken: null, error: null });
  },

  async signUp({ email, password, role, firstName, lastName }) {
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
      const session = await api.signUp({ email, password, role, firstName, lastName });
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
          : // The server's own message is the useful one here: it distinguishes
            // "already registered" from a password the rules rejected.
            (e instanceof ApiFailure ? e.message : 'We could not create your account. Try again.'),
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
      mfaToken: null,
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
