import { Platform } from 'react-native';
import Constants from 'expo-constants';

import { companyNameFromEmail, isPersonalEmailDomain } from '@/domain/email';
import type { AuditReport, AuditRun, AuditStatus, Verdict } from '@/domain/audit';
import type { DiscoveredStartup } from '@/domain/discovery';
import type { Interest, InterestStatus } from '@/domain/interest';
import type { MentorChatResult, MentorCitation, MentorCitationKind } from '@/domain/mentor';
import type {
  DocumentKind,
  EvidenceSubmission,
  ReadinessSummary,
  ReadinessTask,
  RegistryEntry,
  StartupDocument,
  TaskRequirement,
  TaskStatus,
} from '@/domain/readiness';
import {
  fromWireProfile,
  toWireProfile,
  type ServerStage,
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

const WATCHLIST_KEY = 'saci.fundme.watchlist';

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

  // Release/EAS builds have no Metro host. Falling back to localhost here is
  // what made the first APK unusable on a phone — require the public URL.
  if (typeof __DEV__ !== 'undefined' && !__DEV__) {
    throw new Error(
      'EXPO_PUBLIC_API_URL is missing from this build. Set it on the EAS ' +
        'environment for this profile (plaintext or sensitive) and rebuild.',
    );
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

/** Authenticated binary download (PDF). Retries once through refresh on 401. */
async function requestBytes(path: string): Promise<Uint8Array> {
  const current = await loadTokens();
  if (!current) throw new ApiFailure('unauthorized', 'You are signed out.');

  let response = await send(path, { auth: true }, current.access);

  if (response.status === 401) {
    const next = await refreshTokens();
    response = await send(path, { auth: true }, next.access);
  }

  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as ErrorEnvelope | null;
    throw failureFor(response.status, body);
  }

  return new Uint8Array(await response.arrayBuffer());
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
  /** Server-authoritative trial end (ISO UTC). Do not recompute locally. */
  trial_ends_at: string;
  has_access: boolean;
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
      'Admin accounts are managed in the FundReady AI console, not in the app.',
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

/**
 * The founder's startup id, for the endpoints nested under it.
 *
 * Every audit route is `/v1/startups/{id}/…`, and the id is not something the
 * app stores — it comes from `/v1/startups/me`. A founder who has not
 * onboarded gets a named failure rather than a request to `/startups/null/…`,
 * which the server would answer with an unhelpful `422`.
 */
async function requireProfileId(): Promise<string> {
  const profile = await ownProfile();
  if (!profile) {
    throw new ApiFailure(
      'not_found',
      'Complete your startup profile before requesting an audit.',
    );
  }
  return profile.id;
}

// ── audit wire shapes ───────────────────────────────────────

type WireAuditRun = {
  id: string;
  startup_id: string;
  status: AuditStatus;
  rubric_version: string;
  attempts: number;
  error_code: string | null;
  error_message: string | null;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
};

type WireVerdict = {
  scope: string;
  level: string;
  score: number | null;
  sufficiency: string;
  rationale: string;
  evidenced_dimensions: string[];
  unevidenced_dimensions: string[];
};

type WireFounderReport = {
  rubric_version: string;
  data_integrity_score: string;
  fundability: WireVerdict;
  saleability: WireVerdict;
  findings: { code: string; severity: string; fields: string[]; message: string }[];
  action_plan: {
    dimension: string;
    action: string;
    dimension_score: number | null;
    is_priority: boolean;
  }[];
};

function toAuditRun(wire: WireAuditRun): AuditRun {
  return {
    id: wire.id,
    startupId: wire.startup_id,
    status: wire.status,
    rubricVersion: wire.rubric_version,
    attempts: wire.attempts,
    errorCode: wire.error_code,
    errorMessage: wire.error_message,
    createdAt: wire.created_at,
    startedAt: wire.started_at,
    completedAt: wire.completed_at,
  };
}

function toVerdict(wire: WireVerdict): Verdict {
  return {
    scope: wire.scope,
    level: wire.level,
    // Passed through, `null` and all. A `?? 0` here would turn "could not
    // tell" into a scored zero, which is the false verdict the whole audit
    // is built to avoid.
    score: wire.score,
    sufficiency: wire.sufficiency,
    rationale: wire.rationale,
    evidencedDimensions: wire.evidenced_dimensions ?? [],
    unevidencedDimensions: wire.unevidenced_dimensions ?? [],
  };
}

function toAuditReport(wire: WireFounderReport): AuditReport {
  return {
    rubricVersion: wire.rubric_version,
    dataIntegrityScore: wire.data_integrity_score,
    fundability: toVerdict(wire.fundability),
    saleability: toVerdict(wire.saleability),
    findings: (wire.findings ?? []).map((f) => ({
      code: f.code,
      severity: f.severity,
      fields: f.fields ?? [],
      message: f.message,
    })),
    actionPlan: (wire.action_plan ?? []).map((a) => ({
      dimension: a.dimension,
      action: a.action,
      dimensionScore: a.dimension_score,
      isPriority: a.is_priority,
    })),
  };
}

type WireMentorChat = {
  reply: string;
  citations: { kind: string; ref: string }[];
};

function toMentorChat(wire: WireMentorChat): MentorChatResult {
  const kinds = new Set<MentorCitationKind>(['finding', 'task', 'verdict', 'profile']);
  const citations: MentorCitation[] = (wire.citations ?? [])
    .filter((c) => kinds.has(c.kind as MentorCitationKind) && typeof c.ref === 'string')
    .map((c) => ({ kind: c.kind as MentorCitationKind, ref: c.ref }));
  return { reply: wire.reply, citations };
}

// ── discovery wire shapes ───────────────────────────────────

type WireDiscoveryVerdict = { scope: string; level: string; score: number | null };

type WireStartupCard = {
  startup_id: string;
  name: string | null;
  sector: string | null;
  stage: ServerStage | null;
  country: string | null;
  audit_run_id: string;
  rubric_version: string;
  fundability: WireDiscoveryVerdict;
  saleability: WireDiscoveryVerdict;
  published_at: string | null;
};

type WireDiscoveryPage = {
  items: WireStartupCard[];
  total: number;
  limit: number;
  offset: number;
};

function toDiscovered(wire: WireStartupCard): DiscoveredStartup {
  return {
    startupId: wire.startup_id,
    name: wire.name,
    sector: wire.sector,
    stage: wire.stage,
    country: wire.country,
    auditRunId: wire.audit_run_id,
    rubricVersion: wire.rubric_version,
    fundability: wire.fundability,
    saleability: wire.saleability,
    publishedAt: wire.published_at,
  };
}

type WireInterest = {
  id: string;
  startup_id: string;
  status: InterestStatus;
  note: string | null;
  created_at: string;
  decided_at: string | null;
  revealed_run_ids: string[];
};

function toInterest(wire: WireInterest): Interest {
  return {
    id: wire.id,
    startupId: wire.startup_id,
    status: wire.status,
    note: wire.note,
    createdAt: wire.created_at,
    decidedAt: wire.decided_at,
    revealedRunIds: wire.revealed_run_ids ?? [],
  };
}

type WireRegistry = {
  country: string;
  country_name: string;
  registrar: string;
  short_name: string;
  document_name: string;
  number_label: string;
  number_example: string;
};

function toRegistry(wire: WireRegistry): RegistryEntry {
  return {
    country: wire.country,
    countryName: wire.country_name,
    registrar: wire.registrar,
    shortName: wire.short_name,
    documentName: wire.document_name,
    numberLabel: wire.number_label,
    numberExample: wire.number_example,
  };
}

type WireUploadTicket = {
  document_id: string;
  upload_url: string;
  expires_in: number;
  max_bytes: number;
};

type WireDocument = {
  id: string;
  startup_id: string;
  kind: DocumentKind;
  filename: string;
  content_type: string | null;
  size_bytes: number | null;
  status: StartupDocument['status'];
  scan_status: StartupDocument['scanStatus'];
  created_at: string;
  updated_at: string;
};

function toDocument(wire: WireDocument): StartupDocument {
  return {
    id: wire.id,
    startupId: wire.startup_id,
    kind: wire.kind,
    filename: wire.filename,
    contentType: wire.content_type,
    sizeBytes: wire.size_bytes,
    status: wire.status,
    scanStatus: wire.scan_status,
    createdAt: wire.created_at,
    updatedAt: wire.updated_at,
  };
}

type WireTask = {
  id: string;
  startup_id: string;
  audit_run_id: string | null;
  dimension: string;
  action: string;
  requirement: TaskRequirement;
  status: TaskStatus;
  dimension_score: number | null;
  is_priority: boolean;
  assessment_attempts: number;
  attempts_remaining: number;
  created_at: string;
  updated_at: string;
};

type WireTaskPage = {
  items: WireTask[];
  total: number;
  limit: number;
  offset: number;
};

type WireSummary = {
  total: number;
  required_total: number;
  required_open: number;
  required_passed: number;
  recommended_total: number;
  has_audit: boolean;
  gate_cleared: boolean;
  discoverable: boolean;
};

function toTask(wire: WireTask): ReadinessTask {
  return {
    id: wire.id,
    startupId: wire.startup_id,
    auditRunId: wire.audit_run_id,
    dimension: wire.dimension,
    action: wire.action,
    requirement: wire.requirement,
    status: wire.status,
    dimensionScore: wire.dimension_score,
    isPriority: wire.is_priority,
    assessmentAttempts: wire.assessment_attempts,
    attemptsRemaining: wire.attempts_remaining,
    createdAt: wire.created_at,
    updatedAt: wire.updated_at,
  };
}

function toSummary(wire: WireSummary): ReadinessSummary {
  return {
    total: wire.total,
    requiredTotal: wire.required_total,
    requiredOpen: wire.required_open,
    requiredPassed: wire.required_passed,
    recommendedTotal: wire.recommended_total,
    hasAudit: wire.has_audit,
    gateCleared: wire.gate_cleared,
    discoverable: wire.discoverable,
  };
}

type WireEvidenceTicket = {
  evidence_id: string;
  upload_url: string;
  expires_in: number;
  max_bytes: number;
};

type WireEvidence = {
  id: string;
  task_id: string;
  filename: string;
  content_type: string | null;
  size_bytes: number | null;
  status: EvidenceSubmission['status'];
  outcome: EvidenceSubmission['outcome'];
  reasons: string[] | null;
  assessed_at: string | null;
  error_code: string | null;
  created_at: string;
};

type WireEvidencePage = {
  items: WireEvidence[];
  total: number;
  limit: number;
  offset: number;
};

function toEvidence(wire: WireEvidence): EvidenceSubmission {
  return {
    id: wire.id,
    taskId: wire.task_id,
    filename: wire.filename,
    contentType: wire.content_type,
    sizeBytes: wire.size_bytes,
    status: wire.status,
    outcome: wire.outcome,
    reasons: wire.reasons,
    assessedAt: wire.assessed_at,
    errorCode: wire.error_code,
    createdAt: wire.created_at,
  };
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

  async resetPassword(email: string, code: string, password: string) {
    await request<void>('/v1/auth/password-reset/confirm', {
      method: 'POST',
      body: {
        email: email.trim().toLowerCase(),
        code: code.replace(/[\s-]/g, ''),
        password,
      },
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

    return {
      emailVerified: me.email_verified,
      // The stored name first; the domain guess only until one exists. The
      // server fills the name in from the verified company domain at
      // registration (T1.4a), so in practice this falls back rarely.
      companyName: profile?.name || companyNameFromEmail(me.email),
      // No company-registration status on the server yet. Keep the field for
      // UI copy, but do not use it to lock the product (see domain/access.ts).
      verification: 'unverified',
      registration: (() => {
        const mapped = profile ? fromWireProfile(profile) : null;
        if (!mapped?.legalName && !mapped?.registrationNumber) return null;
        return {
          country: mapped?.location || profile?.country || '',
          legalName: mapped?.legalName || '',
          registrationNumber: mapped?.registrationNumber || '',
          registrar: mapped?.registrar || '',
          document: '',
        };
      })(),
      trialEndsAt: me.trial_ends_at,
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
  // The email carries a six-digit code, not a link. Neither call is
  // authenticated, deliberately: whoever is verifying may have registered on a
  // laptop and be reading the mail on a phone, and requiring a session would
  // close the only door they have.
  async confirmEmail(email: string, code: string) {
    await request<void>('/v1/auth/verify-email', {
      method: 'POST',
      body: {
        email: email.trim().toLowerCase(),
        // Sent as typed apart from whitespace and hyphens, which the server
        // ignores anyway — stripping them here means a pasted "123 456" does
        // not fail a length check on the way out.
        code: code.replace(/[\s-]/g, ''),
      },
    });
  },

  async resendVerificationEmail(email: string) {
    // Always 202 — no account, already verified, and asked-again-too-soon are
    // one answer. Nothing here can be reported as "sent".
    await request<unknown>('/v1/auth/verify-email/resend', {
      method: 'POST',
      body: { email: email.trim().toLowerCase() },
    });
  },

  /** Exchange the login challenge and a code for a real session. */
  async verifyMfa(mfaToken: string, code: string) {
    const pair = await request<TokenPair>('/v1/auth/mfa/verify', {
      method: 'POST',
      body: { mfa_token: mfaToken, code: code.trim() },
    });
    return establish(pair);
  },

  async beginMfaEnrolment() {
    const body = await request<{ secret: string; provisioning_uri: string }>(
      '/v1/auth/mfa/enroll',
      { method: 'POST', auth: true },
    );
    return { secret: body.secret, provisioningUri: body.provisioning_uri };
  },

  async confirmMfaEnrolment(code: string) {
    const body = await request<{ recovery_codes: string[] }>('/v1/auth/mfa/confirm', {
      method: 'POST',
      body: { code: code.trim() },
      auth: true,
    });
    return body.recovery_codes ?? [];
  },

  // ── verification ────────────────────────────────────────
  submitCompanyRegistration: () => notYet('Company verification', 'T1.4'),
  submitInvestorCredentials: () => notYet('Investor verification', 'T4.1'),

  // ── billing ─────────────────────────────────────────────
  async purchaseUnlock() {
    const body = await request<{ checkout_url: string; session_id: string }>(
      '/v1/billing/checkout',
      { method: 'POST', auth: true },
    );
    return { checkoutUrl: body.checkout_url, sessionId: body.session_id };
  },

  async getUnlockReceipt() {
    try {
      const body = await request<{
        reference: string;
        amount: number;
        currency: string;
        paid_at: string;
      }>('/v1/billing/unlock', { auth: true });
      return {
        reference: body.reference,
        amount: body.amount,
        currency: body.currency,
        paidAt: body.paid_at,
      };
    } catch (error) {
      if (error instanceof ApiFailure && error.code === 'not_found') return null;
      throw error;
    }
  },

  // ── founder ─────────────────────────────────────────────
  /**
   * The prototype's 0-100 score with weighted parts, VC/PE fit and a colour
   * band. **The server has no such thing and never will** — its audit returns
   * verdicts with nullable scores, a sufficiency and a rationale. Producing an
   * `Assessment` from a `FounderReport` would mean inventing the parts that do
   * not exist. Use `requestAudit` / `getAuditReport` instead; this stays
   * unimplemented so nothing silently falls back to a fabricated score.
   */
  submitAssessment: () => notYet('The prototype score', 'superseded by requestAudit'),

  async requestAudit() {
    const startupId = await requireProfileId();
    return toAuditRun(
      await request<WireAuditRun>(`/v1/startups/${startupId}/audits`, {
        method: 'POST',
        auth: true,
      }),
    );
  },

  async getAuditRun(runId: string) {
    const startupId = await requireProfileId();
    return toAuditRun(
      await request<WireAuditRun>(`/v1/startups/${startupId}/audits/${runId}`, { auth: true }),
    );
  },

  async listAuditRuns() {
    const startupId = await requireProfileId();
    const rows = await request<WireAuditRun[]>(`/v1/startups/${startupId}/audits`, { auth: true });
    return rows.map(toAuditRun);
  },

  async getAuditReport(runId: string) {
    const startupId = await requireProfileId();
    return toAuditReport(
      await request<WireFounderReport>(`/v1/startups/${startupId}/audits/${runId}/report`, {
        auth: true,
      }),
    );
  },

  async getAuditReportPdf(runId: string) {
    const startupId = await requireProfileId();
    return requestBytes(`/v1/startups/${startupId}/audits/${runId}/report.pdf`);
  },

  // ── investor visibility ─────────────────────────────────
  async publishProfile() {
    const startupId = await requireProfileId();
    await request<unknown>(`/v1/startups/${startupId}/publish`, { method: 'POST', auth: true });
  },

  async unpublishProfile() {
    const startupId = await requireProfileId();
    await request<unknown>(`/v1/startups/${startupId}/unpublish`, { method: 'POST', auth: true });
  },

  async getVisibility() {
    const profile = await ownProfile();
    if (!profile) {
      return { investorVisible: false, publishedAt: null };
    }
    return {
      investorVisible: Boolean(profile.investor_visible),
      publishedAt: profile.published_at ?? null,
    };
  },

  async listRegistries() {
    const body = await request<{ registries: WireRegistry[] }>('/v1/registries', { auth: true });
    return (body.registries ?? []).map(toRegistry);
  },

  async beginDocumentUpload(input) {
    const startupId = await requireProfileId();
    const ticket = await request<WireUploadTicket>(`/v1/startups/${startupId}/documents`, {
      method: 'POST',
      body: {
        kind: input.kind,
        filename: input.filename,
        content_type: input.contentType,
      },
      auth: true,
    });
    return {
      documentId: ticket.document_id,
      uploadUrl: ticket.upload_url,
      expiresIn: ticket.expires_in,
      maxBytes: ticket.max_bytes,
    };
  },

  async completeDocumentUpload(documentId) {
    return toDocument(
      await request<WireDocument>(`/v1/documents/${documentId}/complete`, {
        method: 'POST',
        auth: true,
      }),
    );
  },

  async listDocuments() {
    const startupId = await requireProfileId();
    const rows = await request<WireDocument[]>(`/v1/startups/${startupId}/documents`, {
      auth: true,
    });
    return (rows ?? []).map(toDocument);
  },

  async getDocumentDownloadUrl(documentId) {
    const ticket = await request<{ download_url: string; expires_in: number }>(
      `/v1/documents/${documentId}/download`,
      { auth: true },
    );
    return { downloadUrl: ticket.download_url, expiresIn: ticket.expires_in };
  },

  async getTasksSummary() {
    const startupId = await requireProfileId();
    return toSummary(
      await request<WireSummary>(`/v1/startups/${startupId}/tasks/summary`, { auth: true }),
    );
  },

  async listTasks(query = {}) {
    const startupId = await requireProfileId();
    const params = new URLSearchParams();
    if (query.status) params.set('status', query.status);
    if (query.requirement) params.set('requirement', query.requirement);
    params.set('limit', String(query.limit ?? 50));
    params.set('offset', String(query.offset ?? 0));
    const page = await request<WireTaskPage>(
      `/v1/startups/${startupId}/tasks?${params.toString()}`,
      { auth: true },
    );
    return {
      items: (page.items ?? []).map(toTask),
      total: page.total,
      limit: page.limit,
      offset: page.offset,
    };
  },

  async getTask(taskId) {
    const startupId = await requireProfileId();
    return toTask(
      await request<WireTask>(`/v1/startups/${startupId}/tasks/${taskId}`, { auth: true }),
    );
  },

  async beginEvidenceUpload(taskId, input) {
    const ticket = await request<WireEvidenceTicket>(`/v1/tasks/${taskId}/evidence`, {
      method: 'POST',
      body: { filename: input.filename, content_type: input.contentType },
      auth: true,
    });
    return {
      evidenceId: ticket.evidence_id,
      uploadUrl: ticket.upload_url,
      expiresIn: ticket.expires_in,
      maxBytes: ticket.max_bytes,
    };
  },

  async completeEvidenceUpload(evidenceId) {
    return toEvidence(
      await request<WireEvidence>(`/v1/evidence/${evidenceId}/complete`, {
        method: 'POST',
        auth: true,
      }),
    );
  },

  async listEvidence(taskId, query = {}) {
    const params = new URLSearchParams();
    params.set('limit', String(query.limit ?? 50));
    params.set('offset', String(query.offset ?? 0));
    const page = await request<WireEvidencePage>(
      `/v1/tasks/${taskId}/evidence?${params.toString()}`,
      { auth: true },
    );
    return {
      items: (page.items ?? []).map(toEvidence),
      total: page.total,
      limit: page.limit,
      offset: page.offset,
    };
  },

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

  async askMentor(question: string) {
    const result = await httpApi.chatMentor({ message: question });
    return result.reply;
  },

  async chatMentor(input) {
    const startupId = await requireProfileId();
    const wire = await request<WireMentorChat>(`/v1/startups/${startupId}/mentor/chat`, {
      method: 'POST',
      body: {
        message: input.message,
        history: (input.history ?? []).map((turn) => ({
          role: turn.role,
          content: turn.content,
        })),
      },
      auth: true,
    });
    return toMentorChat(wire);
  },

  // ── investor ────────────────────────────────────────────
  /**
   * The prototype's rich dealflow card — MRR, growth, margin, LTV/CAC, runway,
   * team, memos, risk flags. **The summary tier carries none of it**, by
   * design: that is all full-report material and reaches an investor only
   * after an admin reveal. Building a `Company` from `/v1/discover` would mean
   * inventing every number on the card, so these stay unimplemented and
   * `discoverStartups` serves what the server will actually give. Reconciling
   * the screens is F4.2.
   */
  listCompanies: () => notYet('Dealflow in the prototype shape', 'use discoverStartups (F4.2)'),
  getCompany: () => notYet('Company detail in the prototype shape', 'use getDiscoveredStartup'),

  async discoverStartups(query) {
    const params = new URLSearchParams();
    if (query.sector) params.set('sector', query.sector);
    if (query.stage) params.set('stage', query.stage);
    if (query.country) params.set('country', query.country);
    params.set('limit', String(query.limit ?? 20));
    params.set('offset', String(query.offset ?? 0));

    const page = await request<WireDiscoveryPage>(`/v1/discover?${params.toString()}`, {
      auth: true,
    });
    return {
      items: (page.items ?? []).map(toDiscovered),
      total: page.total,
      limit: page.limit,
      offset: page.offset,
    };
  },

  async getDiscoveredStartup(startupId: string) {
    return toDiscovered(await request<WireStartupCard>(`/v1/discover/${startupId}`, { auth: true }));
  },

  async expressInterest(startupId: string, note?: string) {
    const wire = await request<WireInterest>(`/v1/discover/${startupId}/interest`, {
      method: 'POST',
      // Explicitly null rather than omitted: the field is nullable server-side
      // and sending nothing at all makes the body shape depend on the caller.
      body: { note: note?.trim() || null },
      auth: true,
    });
    return toInterest(wire);
  },

  async listInterests(status?: InterestStatus) {
    const params = status ? `?status=${encodeURIComponent(status)}` : '';
    const rows = await request<WireInterest[]>(`/v1/interests${params}`, { auth: true });
    return (rows ?? []).map(toInterest);
  },

  async getRevealedReport(interestId: string, runId: string) {
    return toAuditReport(
      await request<WireFounderReport>(`/v1/interests/${interestId}/reports/${runId}`, {
        auth: true,
      }),
    );
  },

  async getWatchlist() {
    const raw = await storage.get(WATCHLIST_KEY);
    if (!raw) return [];
    try {
      const parsed = JSON.parse(raw) as unknown;
      return Array.isArray(parsed) ? parsed.filter((x): x is string => typeof x === 'string') : [];
    } catch {
      return [];
    }
  },

  async toggleWatch(startupId: string) {
    const before = await httpApi.getWatchlist();
    const next = before.includes(startupId)
      ? before.filter((id) => id !== startupId)
      : [...before, startupId];
    await storage.set(WATCHLIST_KEY, JSON.stringify(next));
    return next;
  },

  requestIntroduction: () => notYet('Introductions', 'use expressInterest (T4.5)'),

  // ── virtual calls ───────────────────────────────────────
  requestCall: () => notYet('Call scheduling', 'T4.5'),
  listCallRequests: () => notYet('Call requests', 'T4.5'),
  respondToCall: () => notYet('Call requests', 'T4.5'),

  // ── notifications ───────────────────────────────────────
  listNotifications: () => notYet('Notifications', 'T5.3'),
  markNotificationsRead: () => notYet('Notifications', 'T5.3'),
};
