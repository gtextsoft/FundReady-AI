import { Platform } from 'react-native';
import Constants from 'expo-constants';

import { companyNameFromEmail, isPersonalEmailDomain } from '@/domain/email';
import {
  fromWireProfile,
  toWireProfile,
  type WireProfileResponse,
} from './profile-mapping';
import { storage } from '@/lib/storage';
import type { VerificationStatus } from '@/domain/types';
import type {
  Credentials,
  DomainLookup,
  FundMeApi,
  Session,
} from './contract';
import { ApiFailure } from './contract';
import { TRIAL_DAYS } from '@/domain/access';

/**
 * The real backend.
 *
 * Live today: authentication (register, login, refresh, logout,
 * `/v1/users/me`), email verification, password reset, MFA, and the Startup
 * Profile (`/v1/startups`). Every other method on `FundMeApi` has no endpoint
 * behind it yet, so it throws `not_implemented` rather than inventing an
 * answer — screens render an explicit "not available yet" state instead of
 * showing numbers nobody computed.
 *
 * As each backend task lands (TASKS.md), replace the matching `notYet(...)`
 * with a real call. The contract and the screens do not change.
 */

/** The API port. Only used when the host is inferred rather than configured. */
const DEV_API_PORT = 8000;

/**
 * Where the API lives.
 *
 * `EXPO_PUBLIC_API_URL` wins when it is set -- that is what staging and
 * production will use. With it unset, the host is taken from whatever address
 * served this bundle and the API port substituted.
 *
 * That inference exists because a phone cannot reach `localhost` (on a device,
 * that is the device), so development otherwise needs the machine's LAN
 * address baked in at bundle time -- and DHCP moves it. Reusing the dev
 * server's own host means the app follows the machine wherever it lands, with
 * no edit and no rebuild.
 */
function resolveBaseUrl(): string {
  const configured = process.env.EXPO_PUBLIC_API_URL?.trim();
  if (configured) return configured.replace(/\/+$/, '');

  // Native (Expo Go): the dev server's address, e.g. "192.168.0.139:8081".
  // Populated only in a development build, which is exactly when it is wanted.
  const hostUri = Constants.expoConfig?.hostUri ?? Constants.expoGoConfig?.debuggerHost;
  const fromExpo = hostUri?.split('/')[0]?.split(':')[0];
  if (fromExpo) return `http://${fromExpo}:${DEV_API_PORT}`;

  // Web: `hostUri` is not populated there, so read the address the page was
  // actually served from. Without this branch a LAN-served web preview calls
  // localhost, which the browser then blocks as a private-network request.
  if (Platform.OS === 'web' && typeof globalThis.location !== 'undefined') {
    const { hostname, protocol } = globalThis.location;
    if (hostname) return `${protocol}//${hostname}:${DEV_API_PORT}`;
  }

  return `http://localhost:${DEV_API_PORT}`;
}

const BASE_URL = resolveBaseUrl();

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

/**
 * Login does not return tokens directly.
 *
 * `authenticated` carries them; `mfa_required` carries a short-lived
 * `mfa_token` instead, which grants nothing until it is exchanged along with a
 * code at `/v1/auth/mfa/verify`. Branch on `status` -- never assume `tokens`.
 */
type LoginResponse = {
  status: 'authenticated' | 'mfa_required';
  tokens: TokenPair | null;
  mfa_token: string | null;
};

/**
 * Raised when the password was right but a second factor is outstanding.
 * The session store catches it and sends the user to the code screen.
 */
export class MfaRequired extends Error {
  readonly mfaToken: string;

  constructor(mfaToken: string) {
    super('A verification code is required to finish signing in.');
    this.name = 'MfaRequired';
    this.mfaToken = mfaToken;
  }
}

type MeResponse = {
  id: string;
  email: string;
  // Nullable: accounts created before the columns existed carry no name.
  first_name: string | null;
  last_name: string | null;
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
  const firstName = me.first_name ?? '';
  const lastName = me.last_name ?? '';
  const given = `${firstName} ${lastName}`.trim();

  // Accounts predating the name columns carry none, so fall back to the
  // address rather than showing an empty header.
  const handle = me.email.split('@')[0] || 'there';
  const fromEmail = handle.replace(/[._-]+/g, ' ').replace(/\b\w/g, (m) => m.toUpperCase());

  return {
    token: tokens?.access ?? '',
    userId: me.id,
    email: me.email,
    role: me.role,
    firstName,
    lastName,
    displayName: given || fromEmail,
  };
}

/** Store a fresh pair and resolve who it belongs to. */
async function establish(pair: TokenPair): Promise<Session> {
  await saveTokens({ access: pair.access_token, refresh: pair.refresh_token });
  try {
    return sessionFrom(await fetchMe());
  } catch (error) {
    // An admin (or an unreadable account) must not keep a live session.
    await clearTokens();
    throw error;
  }
}

async function logIn(creds: Credentials): Promise<Session> {
  const result = await request<LoginResponse>('/v1/auth/login', {
    method: 'POST',
    body: { email: creds.email.trim().toLowerCase(), password: creds.password },
  });

  if (result.status === 'mfa_required') {
    if (!result.mfa_token) {
      throw new ApiFailure('server', 'The server asked for a code but sent no challenge.');
    }
    throw new MfaRequired(result.mfa_token);
  }

  if (!result.tokens) {
    throw new ApiFailure('server', 'The server reported success but returned no tokens.');
  }
  return establish(result.tokens);
}

/**
 * The founder's own startup profile, or null when they have not made one.
 *
 * A `404` here is the ordinary "not onboarded yet" answer, not a failure — the
 * endpoint deliberately returns it rather than an empty object, so there is no
 * way to confuse "no profile" with "a profile with nothing in it".
 */
async function ownProfile(): Promise<WireProfileResponse | null> {
  try {
    return await request<WireProfileResponse>('/v1/startups/me', { auth: true });
  } catch (error) {
    if (error instanceof ApiFailure && error.code === 'not_found') return null;
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
    // The server enforces this too (T1.4a), and it is the authority — a client
    // check can always be bypassed. This one exists to answer instantly and to
    // name the reason, rather than surfacing a bare 422 after a round trip.
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

  async requestPasswordReset(email: string) {
    // Always 202, whether or not the address has an account.
    await request<unknown>('/v1/auth/password-reset/request', {
      method: 'POST',
      body: { email: email.trim().toLowerCase() },
    });
  },

  async resetPassword(token: string, password: string) {
    await request<void>('/v1/auth/password-reset/confirm', {
      method: 'POST',
      body: { token: token.trim(), password },
    });
    // The server has just revoked every refresh token and invalidated every
    // access token it had issued, so anything this device is still holding is
    // dead. Dropping it here is what keeps the app from spending the next
    // request discovering that — and, if a *different* person completed the
    // reset, from leaving a live-looking session on a device they now control.
    await clearTokens();
  },

  // ── accounts ────────────────────────────────────────────
  async getFounderAccount() {
    // Two calls rather than one, deliberately. The company name now has a real
    // home (T1.4), and a name read off a stored profile beats one guessed from
    // an email domain everywhere it is shown. The profile read is tolerant:
    // a founder who has not onboarded has no profile, which is not an error.
    const [me, profile] = await Promise.all([
      fetchMe(),
      ownProfile().catch(() => null),
    ]);
    const created = new Date(me.created_at).getTime();

    return {
      emailVerified: me.email_verified,
      // The stored name first; the domain guess only until one exists. The
      // server fills the name in from the verified company domain at
      // registration (T1.4a), so in practice this falls back rarely.
      companyName: profile?.name || companyNameFromEmail(me.email),
      // Company-registration verification still has no endpoint. This is
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
  // The verification email points at the app, not the API: mail scanners
  // prefetch links, which would spend the single-use token before the person
  // ever clicked. The client lifts the token out and posts it here.
  async confirmEmail(token: string) {
    await request<void>('/v1/auth/verify-email', {
      method: 'POST',
      body: { token: token.trim() },
    });
  },

  // No resend endpoint exists; registration sends the only message so far.
  resendVerificationEmail: () => notYet<void>('Resending the verification email', 'no endpoint yet'),

  /** Exchange the login challenge and a code for a real session. */
  async verifyMfa(mfaToken: string, code: string) {
    const pair = await request<TokenPair>('/v1/auth/mfa/verify', {
      method: 'POST',
      body: { mfa_token: mfaToken, code: code.trim() },
    });
    return establish(pair);
  },

  // ── verification ────────────────────────────────────────
  submitCompanyRegistration: () => notYet('Company verification', 'T1.4'),
  submitInvestorCredentials: () => notYet('Investor verification', 'T4.1'),

  // ── billing ─────────────────────────────────────────────
  purchaseUnlock: () => notYet('Payments', 'T3.3 / T3.4'),

  // ── founder ─────────────────────────────────────────────
  submitAssessment: () => notYet('The fundability assessment', 'Phase 2'),

  async getProfile() {
    const stored = await ownProfile();
    return stored ? fromWireProfile(stored) : null;
  },

  async saveProfile(profile) {
    const { wire, unmapped } = toWireProfile(profile);
    const existing = await ownProfile();

    let saved: WireProfileResponse;
    if (existing) {
      saved = await request<WireProfileResponse>(`/v1/startups/${existing.id}`, {
        method: 'PATCH',
        body: wire,
        auth: true,
      });
    } else {
      try {
        saved = await request<WireProfileResponse>('/v1/startups', {
          method: 'POST',
          body: wire,
          auth: true,
        });
      } catch (error) {
        // One profile per founder. Two devices onboarding at once both see
        // "none yet" and both POST; the loser gets a 409 and should update the
        // profile that now exists rather than report a failure.
        if (!(error instanceof ApiFailure) || error.code !== 'conflict') throw error;
        const created = await ownProfile();
        if (!created) throw error;
        saved = await request<WireProfileResponse>(`/v1/startups/${created.id}`, {
          method: 'PATCH',
          body: wire,
          auth: true,
        });
      }
    }

    return {
      // Read back what was stored rather than echoing what was sent: the
      // server normalises (country upper-cased, unknown fields refused) and
      // the form should show what actually exists.
      profile: fromWireProfile(saved),
      unmapped,
      missingFields: saved.missing_fields ?? [],
    };
  },

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
