import type { AppNotification, CallRequest } from '@/domain/notifications';
import type {
  Assessment,
  Company,
  CompanyRegistration,
  DealflowQuery,
  FounderAccount,
  FounderProfile,
  InvestorAccount,
  InvestorCredentials,
} from '@/domain/types';

/**
 * The complete surface the app needs from the backend.
 *
 * `src/api/mock.ts` implements this against local seed data so the frontend
 * runs standalone. When the real service is ready, add `src/api/http.ts` with
 * the same shape and flip the export in `src/api/index.ts` — no screen changes.
 */

export type Role = 'founder' | 'investor';

export type Session = {
  token: string;
  userId: string;
  email: string;
  /** Chosen at sign-up and fixed thereafter — the two sides never mix. */
  role: Role;
  displayName: string;
};

export type Credentials = { email: string; password: string };

/**
 * Corporate single sign-on for a company domain. This is not consumer social
 * login — it is the identity provider the founder's own company already runs,
 * discovered from the email domain they type.
 */
export type DomainSso = {
  /** Machine name of the identity provider, e.g. 'okta', 'entra', 'google-workspace'. */
  provider: string;
  /** What the button says, e.g. 'Okta'. */
  displayName: string;
};

export type DomainLookup = {
  domain: string;
  /** True when the domain is a consumer mailbox provider, not a company. */
  personal: boolean;
  /** Null when the company has not configured SSO — show the password form. */
  sso: DomainSso | null;
};

export type Page<T> = {
  rows: T[];
  /** Total matching the query, before pagination. */
  total: number;
  page: number;
  perPage: number;
};

/** What the investor list needs — the deep dive fetches the rest. */
export type CompanySummary = Pick<
  Company,
  'id' | 'name' | 'tagline' | 'sector' | 'stage' | 'score' | 'mrr' | 'growth' | 'match'
>;

export type ApiError = { code: 'unauthorized' | 'not_found' | 'validation' | 'network'; message: string };

export type PaymentReceipt = {
  reference: string;
  amount: number;
  currency: string;
  paidAt: string;
};

export interface FundMeApi {
  // ── auth ────────────────────────────────────────────────
  /** Sign in to an existing account. The role comes from the account. */
  signIn(creds: Credentials): Promise<Session>;
  /**
   * Rejects a founder signing up on a consumer mailbox domain. The client
   * checks this too, for an instant answer — but the server is the authority,
   * since the client check can be bypassed.
   */
  signUp(creds: Credentials & { role: Role }): Promise<Session>;
  /**
   * Home-realm discovery: given an email domain, say whether it is a personal
   * provider and whether the company runs single sign-on.
   */
  lookupEmailDomain(domain: string): Promise<DomainLookup>;
  /**
   * Complete sign-up/sign-in through the company's own identity provider.
   * The real implementation opens the IdP in a browser session and exchanges
   * the returned code; nothing about it is consumer social login.
   */
  signInWithSso(domain: string, role: Role): Promise<Session>;
  signOut(): Promise<void>;
  /**
   * Always resolves, whether or not the address has an account — telling a
   * caller which emails are registered is an account-enumeration leak.
   */
  requestPasswordReset(email: string): Promise<void>;

  // ── accounts ────────────────────────────────────────────
  /** Trial window, payment state and verification status for the founder. */
  getFounderAccount(): Promise<FounderAccount>;
  getInvestorAccount(): Promise<InvestorAccount>;

  // ── verification ────────────────────────────────────────
  /** Submits the registration for review; resolves with the new status. */
  submitCompanyRegistration(registration: CompanyRegistration): Promise<FounderAccount>;
  submitInvestorCredentials(credentials: InvestorCredentials): Promise<InvestorAccount>;

  // ── billing ─────────────────────────────────────────────
  /**
   * One-off unlock. The real implementation should hand off to a hosted
   * checkout and never see card data; this resolves once payment settles.
   */
  purchaseUnlock(): Promise<PaymentReceipt>;

  // ── founder ─────────────────────────────────────────────
  /** Persists the profile and returns the scored assessment. */
  submitAssessment(profile: FounderProfile): Promise<Assessment>;
  /** Latest saved profile, or null for a founder who has not onboarded. */
  getProfile(): Promise<FounderProfile | null>;
  enrol(programme: 'readiness' | 'wealth'): Promise<void>;
  /**
   * AI mentor. The mock answers from the founder's own metrics with rules;
   * the real implementation should put an LLM behind this same call so the
   * screen never changes.
   */
  askMentor(question: string): Promise<string>;

  // ── investor ────────────────────────────────────────────
  listCompanies(query: DealflowQuery, page: number, perPage: number): Promise<Page<CompanySummary>>;
  getCompany(id: number): Promise<Company>;
  getWatchlist(): Promise<number[]>;
  toggleWatch(id: number): Promise<number[]>;
  requestIntroduction(companyId: number): Promise<void>;

  // ── virtual calls ───────────────────────────────────────
  /** Investor proposes a slot; the founder is notified. */
  requestCall(input: {
    companyId: number;
    proposedAt: string;
    durationMinutes: number;
    note: string;
  }): Promise<CallRequest>;
  /** Founder's inbox of call requests. */
  listCallRequests(): Promise<CallRequest[]>;
  /** Founder answers; the investor is notified either way. */
  respondToCall(id: string, accept: boolean): Promise<CallRequest>;

  // ── notifications ───────────────────────────────────────
  listNotifications(audience: Role): Promise<AppNotification[]>;
  markNotificationsRead(ids: string[]): Promise<void>;
}
