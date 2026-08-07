import type { AuditReport, AuditRun } from '@/domain/audit';
import type { DiscoveredStartup, DiscoveryPage, DiscoveryQuery } from '@/domain/discovery';
import type { UnmappedAnswer } from './profile-mapping';
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
 * `src/api/http.ts` is the only implementation. Authentication is live; every
 * other method throws `not_implemented` until its endpoint exists, so a screen
 * with no data says so rather than showing something made up.
 */

export type Role = 'founder' | 'investor';

export type Session = {
  token: string;
  userId: string;
  email: string;
  /** Chosen at sign-up and fixed thereafter — the two sides never mix. */
  role: Role;
  firstName: string;
  lastName: string;
  /**
   * "Ada Nwosu" when the account carries a name. Accounts created before names
   * were collected have none, so this falls back to the email local-part —
   * a label to address someone by, never an identity claim.
   */
  displayName: string;
};

export type Credentials = { email: string; password: string };

/** Everything registration needs beyond the credentials themselves. */
export type Registration = Credentials & {
  role: Role;
  firstName: string;
  lastName: string;
};

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

export type ApiErrorCode =
  | 'unauthorized'
  | 'forbidden'
  | 'not_found'
  | 'conflict'
  | 'validation'
  | 'rate_limited'
  | 'server'
  | 'network'
  /** The endpoint does not exist yet. Show the feature as unavailable. */
  | 'not_implemented';

/**
 * Every failure from the API layer. Screens branch on `code`, never on the
 * message — `not_implemented` in particular means "this is not built", which
 * reads very differently to the user than "something went wrong".
 */
export class ApiFailure extends Error {
  readonly code: ApiErrorCode;
  /** The server's own stable error code from the envelope, when it sent one. */
  readonly serverCode?: string;

  constructor(code: ApiErrorCode, message: string, serverCode?: string) {
    super(message);
    this.name = 'ApiFailure';
    this.code = code;
    this.serverCode = serverCode;
  }
}

/** True when a feature has no backend behind it yet. */
export function isUnavailable(error: unknown): error is ApiFailure {
  return error instanceof ApiFailure && error.code === 'not_implemented';
}

/** What came back from a profile save, including what could not be saved. */
export type SaveResult = {
  /** The profile as the server now holds it. */
  profile: FounderProfile;
  /** Answers with no field on the server. See `api/profile-mapping.ts`. */
  unmapped: UnmappedAnswer[];
  /** Fields an audit will still need, computed server-side on every read. */
  missingFields: string[];
};

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
  signUp(registration: Registration): Promise<Session>;
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
  /**
   * Complete the reset with the token from the email and a new password.
   *
   * The token is single-use and expires in an hour; a second attempt with the
   * same one fails. Succeeding **ends every session on every device** — the
   * server revokes all refresh tokens and invalidates the access tokens it has
   * already issued — so the caller must sign in again afterwards, and should
   * say so rather than letting the sign-out look like a fault.
   *
   * Unknown, expired and already-used tokens come back as one indistinguishable
   * `validation` failure, deliberately.
   */
  resetPassword(token: string, password: string): Promise<void>;

  // ── email verification ──────────────────────────────────
  /**
   * Send (or resend) the verification message to the signed-in address.
   *
   * Resolves whether or not anything was sent, for the same anti-enumeration
   * reason as the reset above.
   */
  resendVerificationEmail(): Promise<void>;
  /**
   * Complete verification with the token from the email. Single-use and
   * expiring, so a second attempt with the same token must fail.
   */
  confirmEmail(token: string): Promise<void>;

  // ── two-factor ──────────────────────────────────────────
  /**
   * Finish a login that came back `mfa_required`.
   *
   * Takes the challenge token from that response plus a six-digit
   * authenticator code, or one recovery code. A code is accepted once —
   * replaying it inside its own window is refused.
   */
  verifyMfa(mfaToken: string, code: string): Promise<Session>;

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
  /**
   * Persists the onboarding form, creating the profile on first save.
   *
   * Returns what the server actually stored — read the form back from this
   * rather than assuming it kept what was sent — together with any answers it
   * had no field for. **Show `unmapped` to the founder.** They are answers
   * someone typed that are not being saved, and a screen that stays silent
   * about that is claiming to have stored them.
   */
  saveProfile(profile: FounderProfile): Promise<SaveResult>;

  // ── audit ───────────────────────────────────────────────
  /**
   * Queues an audit of the founder's own profile.
   *
   * Returns immediately with a run in `queued` — the audit itself takes as
   * long as it takes. Poll `getAuditRun` until `isAuditFinished`, then read
   * `getAuditReport`.
   */
  requestAudit(): Promise<AuditRun>;
  /** One run's status. Deliberately carries no findings. */
  getAuditRun(runId: string): Promise<AuditRun>;
  /** Newest first. Empty for a founder who has never been audited. */
  listAuditRuns(): Promise<AuditRun[]>;
  /**
   * The founder-tier report for a finished run.
   *
   * Only meaningful once the run `succeeded`; asking earlier is an error, not
   * an empty report.
   */
  getAuditReport(runId: string): Promise<AuditReport>;

  // ── investor visibility ─────────────────────────────────
  /** Makes the startup discoverable. Requires a cleared audit server-side. */
  publishProfile(): Promise<void>;
  unpublishProfile(): Promise<void>;
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

  /**
   * Discovery, at the tier the server will actually serve.
   *
   * Separate from `listCompanies` on purpose: that one returns the prototype's
   * rich `Company` shape, and the summary tier does not carry enough to build
   * one. See `domain/discovery.ts`.
   */
  discoverStartups(query: DiscoveryQuery): Promise<DiscoveryPage>;
  getDiscoveredStartup(startupId: string): Promise<DiscoveredStartup>;
  /**
   * Registers interest. An admin decides what happens next (T4.5).
   *
   * `note` is context for SACI and **the founder never sees it** — say so in
   * the UI, because an investor writes differently when the subject is not
   * reading. Optional: the server accepts null.
   */
  expressInterest(startupId: string, note?: string): Promise<void>;
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
