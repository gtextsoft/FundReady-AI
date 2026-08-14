export class ApiFailure extends Error {
  readonly code:
    | "unauthorized"
    | "forbidden"
    | "not_found"
    | "conflict"
    | "validation"
    | "rate_limited"
    | "server"
    | "network";
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
