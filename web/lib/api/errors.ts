export class ApiFailure extends Error {
  readonly code:
    | "unauthorized"
    | "forbidden"
    | "not_found"
    | "conflict"
    | "validation"
    | "rate_limited"
    | "server"
    | "network"
    | "not_implemented";
  readonly serverCode?: string;
  readonly details?: Record<string, unknown>;

  constructor(
    code: ApiFailure["code"],
    message: string,
    serverCode?: string,
    details?: Record<string, unknown>,
  ) {
    super(message);
    this.name = "ApiFailure";
    this.code = code;
    this.serverCode = serverCode;
    this.details = details;
  }
}

export class MfaRequired extends Error {
  readonly mfaToken: string;
  constructor(mfaToken: string) {
    super("A verification code is required to finish signing in.");
    this.name = "MfaRequired";
    this.mfaToken = mfaToken;
  }
}

const STATUS_CODES: Record<number, ApiFailure["code"]> = {
  401: "unauthorized",
  403: "forbidden",
  404: "not_found",
  409: "conflict",
  422: "validation",
  429: "rate_limited",
};

export function failureFor(
  status: number,
  body: { error?: { code?: string; message?: string; details?: Record<string, unknown> } } | null,
): ApiFailure {
  const code = STATUS_CODES[status] ?? (status >= 500 ? "server" : "network");
  const message = body?.error?.message ?? `The server returned ${status}.`;
  return new ApiFailure(code, message, body?.error?.code, body?.error?.details);
}

export function isMfaGate(error: unknown): boolean {
  return (
    error instanceof ApiFailure &&
    error.code === "forbidden" &&
    /two-factor|enrol/i.test(error.message)
  );
}

/** True when a feature has no backend behind it yet. */
export function isUnavailable(error: unknown): error is ApiFailure {
  return error instanceof ApiFailure && error.code === "not_implemented";
}

/** Reject locally — do not hit a route the API does not serve. */
export function notYet<T>(feature: string, task: string): Promise<T> {
  return Promise.reject(
    new ApiFailure(
      "not_implemented",
      `${feature} is not available yet — the backend for it has not been built (${task}).`,
    ),
  );
}
