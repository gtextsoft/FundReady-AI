import { companyNameFromEmail, isPersonalEmailDomain } from '@/domain/email';
import { storage } from '@/lib/storage';
import type { VerificationStatus } from '@/domain/types';
import type {
  Credentials,
  DomainLookup,
  FundMeApi,
  Role,
  Session,
} from './contract';
import { ApiFailure } from './contract';
import { TRIAL_DAYS } from '@/domain/access';

/**
 * The real backend.
 *
 * Only authentication exists server-side today: register, login, refresh,
 * logout and `/v1/users/me`. Every other method on `FundMeApi` has no endpoint
 * behind it yet, so it throws `not_implemented` rather than inventing an
 * answer — screens render an explicit "not available yet" state instead of
 * showing numbers nobody computed.
 *
 * As each backend task lands (TASKS.md), replace the matching `notYet(...)`
 * with a real call. The contract and the screens do not change.
 */

const BASE_URL = (process.env.EXPO_PUBLIC_API_URL ?? 'http://localhost:8000').replace(/\/+$/, '');

/** Access + refresh live together; they are only ever valid as a pair. */
const TOKENS_KEY = 'saci.fundme.tokens';

type Tokens = { access: string; refresh: string };

let tokens: Tokens | null = null;
let restored = false;

async function loadTokens(): Promise<Tokens | null> {
  if (restored) return tokens;
  restored = true;
  const raw = await storage.get(TOKENS_KEY);
  if (raw) {
    try {
      tokens = JSON.parse(raw) as Tokens;
    } catch {
      await storage.remove(TOKENS_KEY);
    }
  }
  return tokens;
}

async function saveTokens(next: Tokens): Promise<void> {
  tokens = next;
  restored = true;
  await storage.set(TOKENS_KEY, JSON.stringify(next));
}

async function clearTokens(): Promise<void> {
  tokens = null;
  restored = true;
  await storage.remove(TOKENS_KEY);
}

/** Shape of the API's error envelope (CLAUDE.md section 6). */
type ErrorEnvelope = { error?: { code?: string; message?: string; details?: unknown } };

const STATUS_CODES: Record<number, ApiFailure['code']> = {
  401: 'unauthorized',
  403: 'forbidden',
  404: 'not_found',
  409: 'conflict',
  422: 'validation',
  429: 'rate_limited',
};

function failureFor(status: number, body: ErrorEnvelope | null): ApiFailure {
  const code = STATUS_CODES[status] ?? (status >= 500 ? 'server' : 'network');
  const message = body?.error?.message ?? `The server returned ${status}.`;
  return new ApiFailure(code, message, body?.error?.code);
}

type RequestOptions = {
  method?: 'GET' | 'POST' | 'PATCH' | 'DELETE';
  body?: unknown;
  /** Attach the bearer token and retry once through refresh on a 401. */
  auth?: boolean;
};

async function send(path: string, options: RequestOptions, bearer: string | null): Promise<Response> {
  const headers: Record<string, string> = { Accept: 'application/json' };
  if (options.body !== undefined) headers['Content-Type'] = 'application/json';
  if (bearer) headers.Authorization = `Bearer ${bearer}`;

  try {
    return await fetch(`${BASE_URL}${path}`, {
      method: options.method ?? 'GET',
      headers,
      body: options.body === undefined ? undefined : JSON.stringify(options.body),
    });
  } catch {
    // A transport failure, not an HTTP error — the server was never reached.
    throw new ApiFailure(
      'network',
      `Could not reach the API at ${BASE_URL}. Is the backend running?`,
    );
  }
}

/**
 * The single in-flight refresh.
 *
 * Refresh tokens rotate and the server treats a *second* presentation of the
 * same token as theft: it revokes the whole family and forces a fresh login.
 * Two screens 401-ing at once would do exactly that, so every caller waits on
 * one shared exchange rather than starting its own.
 */
let refreshing: Promise<Tokens> | null = null;

function refreshTokens(): Promise<Tokens> {
  refreshing ??= (async () => {
    const current = await loadTokens();
    if (!current) throw new ApiFailure('unauthorized', 'You are signed out.');

    const response = await send(
      '/v1/auth/refresh',
      { method: 'POST', body: { refresh_token: current.refresh } },
      null,
    );

    if (!response.ok) {
      await clearTokens();
      throw new ApiFailure('unauthorized', 'Your session expired. Please sign in again.');
    }

    const pair = (await response.json()) as { access_token: string; refresh_token: string };
    const next: Tokens = { access: pair.access_token, refresh: pair.refresh_token };
    // Store before returning: the old refresh token is already spent, so
    // losing the new one here would lock the user out.
    await saveTokens(next);
    return next;
  })().finally(() => {
    refreshing = null;
  });

  return refreshing;
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const current = options.auth ? await loadTokens() : null;
  if (options.auth && !current) throw new ApiFailure('unauthorized', 'You are signed out.');

  let response = await send(path, options, current?.access ?? null);

  if (response.status === 401 && options.auth) {
    const next = await refreshTokens();
    response = await send(path, options, next.access);
  }

  if (response.status === 204) return undefined as T;

  const body = (await response.json().catch(() => null)) as (T & ErrorEnvelope) | null;
  if (!response.ok) throw failureFor(response.status, body);
  return body as T;
}

// ── server shapes ───────────────────────────────────────────

type TokenPair = { access_token: string; refresh_token: string; expires_in: number };

type MeResponse = {
  id: string;
  email: string;
  first_name: string;
  last_name: string;
  role: 'founder' | 'investor' | 'admin';
  status: 'pending_verification' | 'active' | 'suspended';
  email_verified: boolean;
  kyc_status: 'none' | 'pending' | 'verified' | 'failed';
  subscription_status: 'none' | 'active' | 'past_due' | 'canceled';
  created_at: string;
};

/**
 * Always refetched, never cached.
 *
 * Account state changes on the server -- an address gets confirmed, a
 * subscription activates -- and the screens re-read it on focus precisely to
 * notice. A cached copy would pin the app to whatever was true at login and
 * leave someone staring at "confirm your email" after they already had.
 */
async function fetchMe(): Promise<MeResponse> {
  return request<MeResponse>('/v1/users/me', { auth: true });
}

/** Stripe Identity states map one-to-one onto the UI's verification states. */
const KYC_TO_VERIFICATION: Record<MeResponse['kyc_status'], VerificationStatus> = {
  none: 'unverified',
  pending: 'in_review',
  verified: 'verified',
  failed: 'rejected',
};

function sessionFrom(me: MeResponse): Session {
  if (me.role === 'admin') {
    throw new ApiFailure(
      'forbidden',
      'Admin accounts are managed in the SACI console, not in the app.',
    );
  }
  const given = `${me.first_name} ${me.last_name}`.trim();
  // Accounts predating the name fields have none; fall back to the address so
  // the UI still has something to address them by.
  const handle = me.email.split('@')[0] || 'there';
  const fromEmail = handle.replace(/[._-]+/g, ' ').replace(/\b\w/g, (m) => m.toUpperCase());

  return {
    token: tokens?.access ?? '',
    userId: me.id,
    email: me.email,
    role: me.role,
    firstName: me.first_name,
    lastName: me.last_name,
    displayName: given || fromEmail,
  };
}

async function logIn(creds: Credentials): Promise<Session> {
  const pair = await request<TokenPair>('/v1/auth/login', {
    method: 'POST',
    body: { email: creds.email.trim().toLowerCase(), password: creds.password },
  });
  await saveTokens({ access: pair.access_token, refresh: pair.refresh_token });
  try {
    return sessionFrom(await fetchMe());
  } catch (error) {
    // An admin (or an unreadable account) must not keep a live session.
    await clearTokens();
    throw error;
  }
}

/** Every method with no endpoint behind it fails the same, nameable way. */
function notYet<T>(feature: string, task: string): Promise<T> {
  return Promise.reject(
    new ApiFailure(
      'not_implemented',
      `${feature} is not available yet — the backend for it has not been built (${task}).`,
    ),
  );
}

export const httpApi: FundMeApi = {
  // ── auth ────────────────────────────────────────────────
  signIn: logIn,

  async signUp({ email, password, role, firstName, lastName }) {
    // NOTE: the server does not yet enforce the company-domain rule for
    // founders, so this check is currently the only one there is. It belongs
    // server-side — a client check can always be bypassed. Flagged in TASKS.md.
    if (role === 'founder' && isPersonalEmailDomain(email.split('@')[1] ?? '')) {
      throw new ApiFailure('validation', 'personal_email_domain');
    }

    // Registration answers 202 with no tokens, and answers identically whether
    // or not the address was already taken, so we cannot tell from it whether
    // an account was created. Logging in straight after is what proves it.
    await request<unknown>('/v1/auth/register', {
      method: 'POST',
      body: {
        email: email.trim().toLowerCase(),
        password,
        role,
        first_name: firstName.trim(),
        last_name: lastName.trim(),
      },
    });

    try {
      return await logIn({ email, password });
    } catch (error) {
      if (error instanceof ApiFailure && error.code === 'unauthorized') {
        throw new ApiFailure(
          'conflict',
          'That address is already registered. Sign in instead, or reset your password.',
        );
      }
      throw error;
    }
  },

  async lookupEmailDomain(domain: string): Promise<DomainLookup> {
    const d = domain.trim().toLowerCase();
    // Resolved on the device: the personal-domain blocklist ships with the app.
    // `sso` is always null because no per-domain identity-provider directory
    // exists server-side — there is no such endpoint and no task for one.
    return { domain: d, personal: isPersonalEmailDomain(d), sso: null };
  },

  signInWithSso: () => notYet<Session>('Single sign-on', 'no backend task yet'),

  async signOut() {
    const current = await loadTokens();
    if (current) {
      // Best effort: a failure here still signs the device out locally.
      await request<void>('/v1/auth/logout', {
        method: 'POST',
        body: { refresh_token: current.refresh },
      }).catch(() => undefined);
    }
    await clearTokens();
  },

  requestPasswordReset: () => notYet<void>('Password reset', 'T1.2b'),

  // ── accounts ────────────────────────────────────────────
  async getFounderAccount() {
    const me = await fetchMe();
    const created = new Date(me.created_at).getTime();
    return {
      emailVerified: me.email_verified,
      // No company record exists server-side yet (T1.4), so this is guessed
      // from the sign-up domain purely as a display default. Anything the
      // founder actually types wins over it everywhere it is shown.
      companyName: companyNameFromEmail(me.email),
      // Company-registration verification has no endpoint yet (T1.4). This is
      // deliberately NOT read off `kyc_status`, which is investor identity.
      verification: 'unverified',
      registration: null,
      trialEndsAt: new Date(created + TRIAL_DAYS * 86_400_000).toISOString(),
      subscriptionStatus: me.subscription_status,
    };
  },

  async getInvestorAccount() {
    const me = await fetchMe();
    return {
      emailVerified: me.email_verified,
      verification: KYC_TO_VERIFICATION[me.kyc_status],
      credentials: null,
    };
  },

  // ── email verification ──────────────────────────────────
  resendVerificationEmail: () => notYet<void>('Email verification', 'T1.2b'),
  confirmEmail: () => notYet<void>('Email verification', 'T1.2b'),

  // ── verification ────────────────────────────────────────
  submitCompanyRegistration: () => notYet('Company verification', 'T1.4'),
  submitInvestorCredentials: () => notYet('Investor verification', 'T4.1'),

  // ── billing ─────────────────────────────────────────────
  purchaseUnlock: () => notYet('Payments', 'T3.3 / T3.4'),

  // ── founder ─────────────────────────────────────────────
  submitAssessment: () => notYet('The fundability assessment', 'Phase 2'),
  getProfile: () => notYet('Your startup profile', 'T1.4'),
  enrol: () => notYet('Programme enrolment', 'T3.2'),
  askMentor: () => notYet('The AI mentor', 'T3.7'),

  // ── investor ────────────────────────────────────────────
  listCompanies: () => notYet('Dealflow', 'T4.2 / T4.3'),
  getCompany: () => notYet('Company detail', 'T4.2'),
  getWatchlist: () => notYet('The watchlist', 'no backend task yet'),
  toggleWatch: () => notYet('The watchlist', 'no backend task yet'),
  requestIntroduction: () => notYet('Introductions', 'T4.5'),

  // ── virtual calls ───────────────────────────────────────
  requestCall: () => notYet('Call scheduling', 'T4.5'),
  listCallRequests: () => notYet('Call requests', 'T4.5'),
  respondToCall: () => notYet('Call requests', 'T4.5'),

  // ── notifications ───────────────────────────────────────
  listNotifications: () => notYet('Notifications', 'T5.3'),
  markNotificationsRead: () => notYet('Notifications', 'T5.3'),
};
