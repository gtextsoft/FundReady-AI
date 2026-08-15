import { ApiFailure, MfaRequired, failureFor } from "./errors";
import type { MeResponse, Session, TokenPair } from "./types";
import { displayName } from "@/lib/utils";

// Same-origin `/v1/*` — Next rewrites these to the Render API. Do not point
// the browser at the upstream host; staging/production CORS is closed.
const BASE = "";

let accessToken: string | null = null;
let refreshing: Promise<string> | null = null;
let refreshAbort: AbortController | null = null;
let authEpoch = 0;

export function setAccessToken(token: string | null) {
  accessToken = token;
}

export function getAccessToken() {
  return accessToken;
}

async function refreshAccess(): Promise<string> {
  const started = authEpoch;
  refreshing ??= (async () => {
    refreshAbort = new AbortController();
    const res = await fetch("/api/auth/refresh", {
      method: "POST",
      credentials: "same-origin",
      cache: "no-store",
      signal: refreshAbort.signal,
    });
    if (started !== authEpoch) {
      throw new ApiFailure("unauthorized", "You are signed out.");
    }
    if (res.status === 204) {
      accessToken = null;
      throw new ApiFailure("unauthorized", "You are signed out.");
    }
    if (!res.ok) {
      accessToken = null;
      throw new ApiFailure("unauthorized", "Your session expired. Please sign in again.");
    }
    const data = (await res.json()) as { access_token: string };
    if (started !== authEpoch) {
      throw new ApiFailure("unauthorized", "You are signed out.");
    }
    accessToken = data.access_token;
    return data.access_token;
  })().finally(() => {
    refreshing = null;
    refreshAbort = null;
  });
  return refreshing;
}

type SendOpts = {
  method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  body?: unknown;
  auth?: boolean;
};

async function send(path: string, opts: SendOpts, bearer: string | null): Promise<Response> {
  const headers: Record<string, string> = { Accept: "application/json" };
  if (opts.body !== undefined) headers["Content-Type"] = "application/json";
  if (bearer) headers.Authorization = `Bearer ${bearer}`;
  try {
    return await fetch(`${BASE}${path}`, {
      method: opts.method ?? "GET",
      headers,
      body: opts.body === undefined ? undefined : JSON.stringify(opts.body),
    });
  } catch {
    throw new ApiFailure("network", "Could not reach the API. Is the backend running?");
  }
}

export async function request<T>(path: string, opts: SendOpts = {}): Promise<T> {
  const auth = opts.auth !== false;
  if (auth && !accessToken) {
    try {
      await refreshAccess();
    } catch {
      throw new ApiFailure("unauthorized", "You are signed out.");
    }
  }

  let res = await send(path, opts, auth ? accessToken : null);
  if (res.status === 401 && auth) {
    const next = await refreshAccess();
    res = await send(path, opts, next);
  }
  if (res.status === 204) return undefined as T;
  const body = (await res.json().catch(() => null)) as (T & {
    error?: { code?: string; message?: string; details?: Record<string, unknown> };
  }) | null;
  if (!res.ok) throw failureFor(res.status, body);
  return body as T;
}

export async function requestBytes(path: string): Promise<Uint8Array> {
  if (!accessToken) await refreshAccess();
  const url = path.startsWith("/api/") ? path : `${BASE}${path}`;
  const headers: Record<string, string> = { Accept: "application/octet-stream" };
  if (accessToken) headers.Authorization = `Bearer ${accessToken}`;
  let res: Response;
  try {
    res = await fetch(url, { headers, cache: "no-store" });
  } catch {
    throw new ApiFailure("network", "Could not download the file.");
  }
  if (res.status === 401) {
    const next = await refreshAccess();
    headers.Authorization = `Bearer ${next}`;
    res = await fetch(url, { headers, cache: "no-store" });
  }
  if (!res.ok) {
    const body = (await res.json().catch(() => null)) as {
      error?: { code?: string; message?: string };
    } | null;
    throw failureFor(res.status, body);
  }
  return new Uint8Array(await res.arrayBuffer());
}

export async function requestStream(
  path: string,
  body: unknown,
  onEvent: (event: string, data: Record<string, unknown>) => void,
): Promise<Record<string, unknown>> {
  if (!accessToken) await refreshAccess();
  const headers: Record<string, string> = {
    Accept: "text/event-stream",
    "Content-Type": "application/json",
  };
  if (accessToken) headers.Authorization = `Bearer ${accessToken}`;
  let res = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers,
    body: JSON.stringify(body),
  });
  if (res.status === 401) {
    const next = await refreshAccess();
    headers.Authorization = `Bearer ${next}`;
    res = await fetch(`${BASE}${path}`, {
      method: "POST",
      headers,
      body: JSON.stringify(body),
    });
  }
  if (!res.ok) {
    const errBody = (await res.json().catch(() => null)) as {
      error?: { code?: string; message?: string };
    } | null;
    throw failureFor(res.status, errBody);
  }
  if (!res.body) throw new ApiFailure("network", "The mentor stream did not start.");

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let donePayload: Record<string, unknown> = {};
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const parts = buffer.split("\n\n");
    buffer = parts.pop() ?? "";
    for (const part of parts) {
      let event = "message";
      const dataLines: string[] = [];
      for (const line of part.split("\n")) {
        if (line.startsWith("event:")) event = line.slice(6).trim();
        if (line.startsWith("data:")) dataLines.push(line.slice(5).trim());
      }
      if (!dataLines.length) continue;
      const data = JSON.parse(dataLines.join("\n")) as Record<string, unknown>;
      if (event === "done") donePayload = data;
      onEvent(event, data);
    }
  }
  return donePayload;
}

export function sessionFrom(me: MeResponse): Session {
  return {
    userId: me.id,
    email: me.email,
    role: me.role,
    firstName: me.first_name ?? "",
    lastName: me.last_name ?? "",
    displayName: displayName(me.first_name, me.last_name, me.email),
    emailVerified: me.email_verified,
    status: me.status,
    kycStatus: me.kyc_status,
    subscriptionStatus: me.subscription_status,
    trialEndsAt: me.trial_ends_at,
    hasAccess: me.has_access,
    mfaEnabled: me.mfa_enabled,
  };
}

export async function fetchMe(): Promise<MeResponse> {
  return request<MeResponse>("/v1/users/me");
}

export async function login(email: string, password: string): Promise<Session> {
  const res = await fetch("/api/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  const data = await res.json().catch(() => null);
  if (!res.ok) throw failureFor(res.status, data);
  if (data.status === "mfa_required") throw new MfaRequired(data.mfa_token);
  setAccessToken(data.access_token);
  return sessionFrom(await fetchMe());
}

export async function verifyMfaLogin(mfaToken: string, code: string): Promise<Session> {
  const res = await fetch("/api/auth/mfa", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ mfa_token: mfaToken, code }),
  });
  const data = await res.json().catch(() => null);
  if (!res.ok) throw failureFor(res.status, data);
  setAccessToken(data.access_token);
  return sessionFrom(await fetchMe());
}

export async function restoreSession(): Promise<Session | null> {
  try {
    await refreshAccess();
    return sessionFrom(await fetchMe());
  } catch {
    setAccessToken(null);
    return null;
  }
}

export async function logout(): Promise<void> {
  authEpoch += 1;
  accessToken = null;
  refreshAbort?.abort();
  const pending = refreshing;
  try {
    await pending;
  } catch {
    /* in-flight refresh is discarded */
  }
  await fetch("/api/auth/logout", {
    method: "POST",
    credentials: "same-origin",
    cache: "no-store",
  }).catch(() => undefined);
  accessToken = null;
}

export async function register(input: {
  email: string;
  password: string;
  role: "founder" | "investor";
  first_name: string;
  last_name: string;
}) {
  return request<{ status: string; message: string }>("/v1/auth/register", {
    method: "POST",
    body: input,
    auth: false,
  });
}

export async function verifyEmail(email: string, code: string) {
  return request<void>("/v1/auth/verify-email", {
    method: "POST",
    body: { email, code },
    auth: false,
  });
}

export async function resendVerification(email: string) {
  return request<void>("/v1/auth/verify-email/resend", {
    method: "POST",
    body: { email },
    auth: false,
  });
}

export async function requestPasswordReset(email: string) {
  return request<void>("/v1/auth/password-reset/request", {
    method: "POST",
    body: { email },
    auth: false,
  });
}

export async function confirmPasswordReset(email: string, code: string, password: string) {
  return request<void>("/v1/auth/password-reset/confirm", {
    method: "POST",
    body: { email, code, password },
    auth: false,
  });
}

export async function enrollMfa() {
  return request<{ secret: string; provisioning_uri: string }>("/v1/auth/mfa/enroll", {
    method: "POST",
  });
}

export async function confirmMfa(code: string) {
  return request<{ recovery_codes: string[] }>("/v1/auth/mfa/confirm", {
    method: "POST",
    body: { code },
  });
}

export type { TokenPair };
