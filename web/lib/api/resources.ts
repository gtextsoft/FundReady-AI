import { request, requestBytes, requestStream } from "./http";

export type WireField = {
  value: string | number | boolean | null;
  source: "founder" | "document" | "inferred";
  confidence?: number | null;
  document_id?: string | null;
};

export type ProfileResponse = {
  id: string;
  owner_id: string;
  name: string | null;
  sector: string | null;
  stage: string | null;
  country: string | null;
  currency: string | null;
  fields: Record<string, WireField>;
  missing_fields: string[];
  investor_visible: boolean;
  published_at: string | null;
  company_verification_status: "none" | "submitted" | "in_review" | "accepted" | "rejected";
  created_at: string;
  updated_at: string;
};

export type AuditRun = {
  id: string;
  startup_id: string;
  status: "queued" | "running" | "succeeded" | "failed";
  rubric_version: string;
  attempts: number;
  error_code: string | null;
  error_message: string | null;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
};

export type Verdict = {
  scope: string;
  level: string;
  score: number | null;
  sufficiency?: string;
  rationale?: string;
  evidenced_dimensions?: string[];
  unevidenced_dimensions?: string[];
};

export type AuditReport = {
  rubric_version: string;
  data_integrity_score: string | number;
  fundability: Verdict;
  saleability: Verdict;
  findings: {
    code: string;
    severity: string;
    fields: string[];
    message: string;
    detail?: string;
  }[];
  action_plan: {
    dimension: string;
    action: string;
    dimension_score: number | null;
    is_priority?: boolean;
  }[];
};

export type ReadinessTask = {
  id: string;
  startup_id: string;
  audit_run_id: string | null;
  dimension: string;
  action: string;
  requirement: "required" | "recommended";
  status: "open" | "submitted" | "passed" | "failed" | "needs_more" | "obsolete";
  dimension_score: number | null;
  is_priority: boolean;
  assessment_attempts: number;
  attempts_remaining: number;
  created_at: string;
  updated_at: string;
};

export type ReadinessSummary = {
  total: number;
  required_total: number;
  required_open: number;
  required_passed: number;
  recommended_total: number;
  has_audit: boolean;
  fundability_score: number | null;
  publish_floor: number;
  score_cleared: boolean;
  gate_cleared: boolean;
  discoverable: boolean;
};

export type Page<T> = { items: T[]; total: number; limit: number; offset: number };

export type StartupCard = {
  startup_id: string;
  name: string | null;
  sector: string | null;
  stage: string | null;
  country: string | null;
  audit_run_id: string;
  rubric_version: string;
  fundability: { scope: string; level: string; score: number | null };
  saleability: { scope: string; level: string; score: number | null };
  published_at: string | null;
};

export type Interest = {
  id: string;
  startup_id: string;
  status: "pending" | "approved" | "declined" | "withdrawn";
  note: string | null;
  created_at: string;
  decided_at: string | null;
  revealed_run_ids: string[];
};

export type Meeting = {
  id: string;
  interest_id: string;
  scheduled_at: string;
  duration_minutes: number;
  location: string | null;
  notes: string | null;
  status: string;
  created_at: string;
};

export type NotificationItem = {
  id: string;
  kind: string;
  title: string;
  body: string;
  payload: Record<string, unknown>;
  read_at: string | null;
  created_at: string;
};

export type Product = {
  id: string;
  kind: string;
  slug: string;
  title: string;
  description: string;
  regions: string[];
  gap_tags: string[];
  amount_minor: number | null;
  currency: string | null;
  event_starts_at: string | null;
  event_location: string | null;
  active: boolean;
  checkout_configured: boolean;
};

export type Enrolment = {
  id: string;
  product_id: string;
  created_at: string;
  product: Product | null;
};

export type InvestorProfile = {
  firm: string | null;
  investor_type: string | null;
  country: string | null;
  linkedin_url: string | null;
  thesis_sectors: string[];
  thesis_stages: string[];
  thesis_geographies: string[];
  ticket_min_minor: number | null;
  ticket_max_minor: number | null;
  ticket_currency: string | null;
  risk_notes: string | null;
  kyc_status: string;
  review_status: "none" | "in_review" | "accepted" | "rejected";
};

export type InvestorReviewCard = {
  user_id: string;
  email: string;
  first_name: string | null;
  last_name: string | null;
  firm: string | null;
  investor_type: string | null;
  country: string | null;
  linkedin_url: string | null;
  thesis_sectors: string[];
  thesis_stages: string[];
  thesis_geographies: string[];
  risk_notes: string | null;
  review_status: InvestorProfile["review_status"];
  updated_at: string | null;
};

export type UserRow = {
  id: string;
  email: string;
  role: "founder" | "investor" | "admin";
  first_name: string | null;
  last_name: string | null;
  status: string;
  email_verified: boolean;
  kyc_status: string;
  subscription_status: string;
  created_at: string;
  trial_ends_at: string;
  has_access: boolean;
  mfa_enabled: boolean;
};

export type Benchmark = {
  id: string;
  sector: string;
  stage: string;
  metric: string;
  region: string;
  p25: string;
  p50: string;
  p75: string;
  sample_size: number | null;
  source: string;
  as_of_date: string;
  is_active: boolean;
};

export type DocumentRow = {
  id: string;
  startup_id: string;
  kind: string;
  filename: string;
  content_type: string | null;
  size_bytes: number | null;
  status: string;
  scan_status: string;
  created_at: string;
  updated_at: string;
};

export type AdminStats = {
  startups_total: number;
  startups_published: number;
  startups_with_succeeded_audit: number;
  users_founders: number;
  users_investors: number;
  users_admins: number;
  interests_pending: number;
};

export type CorpusRecord = {
  startup_id: string;
  sector: string | null;
  stage: string | null;
  country: string | null;
  currency: string | null;
  verification: ProfileResponse["company_verification_status"];
  published: boolean;
  fields: Record<string, unknown>;
  latest_audit: Record<string, unknown> | null;
  tasks: { dimension: string; action: string; status: string; requirement: string }[];
};

export type CorpusPage = Page<CorpusRecord> & { purpose: "model_training" };

export function queryString(params: Record<string, string | number | boolean | undefined | null>) {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === "") continue;
    search.set(key, String(value));
  }
  const encoded = search.toString();
  return encoded ? `?${encoded}` : "";
}

export const api = {
  getProfile: () => request<ProfileResponse>("/v1/startups/me"),
  getProfileById: (id: string) => request<ProfileResponse>(`/v1/startups/${id}`),
  createProfile: (body: Record<string, unknown>) =>
    request<ProfileResponse>("/v1/startups", { method: "POST", body }),
  updateProfile: (id: string, body: Record<string, unknown>) =>
    request<ProfileResponse>(`/v1/startups/${id}`, { method: "PATCH", body }),
  publish: (id: string) =>
    request<ProfileResponse>(`/v1/startups/${id}/publish`, { method: "POST" }),
  unpublish: (id: string) =>
    request<ProfileResponse>(`/v1/startups/${id}/unpublish`, { method: "POST" }),
  submitCompanyVerification: (id: string) =>
    request<ProfileResponse>(`/v1/startups/${id}/company-verification/submit`, {
      method: "POST",
    }),
  decideCompanyVerification: (id: string, accept: boolean) =>
    request<ProfileResponse>(`/v1/admin/startups/${id}/company-verification`, {
      method: "POST",
      body: { accept },
    }),
  listRegistries: () =>
    request<{ registries: { country: string; country_name: string; registrar: string; short_name: string; document_name: string; number_label: string; number_example: string }[] }>(
      "/v1/registries",
    ),
  beginDocumentUpload: (
    startupId: string,
    input: { kind: string; filename: string; content_type: string },
  ) =>
    request<{ document_id: string; upload_url: string; expires_in: number; max_bytes: number }>(
      `/v1/startups/${startupId}/documents`,
      { method: "POST", body: input },
    ),
  completeDocument: (id: string) =>
    request<DocumentRow>(`/v1/documents/${id}/complete`, { method: "POST" }),
  listDocuments: (startupId: string, qs = "") =>
    request<DocumentRow[]>(`/v1/startups/${startupId}/documents${qs}`),

  requestAudit: (startupId: string) =>
    request<AuditRun>(`/v1/startups/${startupId}/audits`, { method: "POST" }),
  listAudits: (startupId: string) =>
    request<AuditRun[]>(`/v1/startups/${startupId}/audits`),
  getAudit: (startupId: string, runId: string) =>
    request<AuditRun>(`/v1/startups/${startupId}/audits/${runId}`),
  getAuditReport: (startupId: string, runId: string) =>
    request<AuditReport>(`/v1/startups/${startupId}/audits/${runId}/report`),
  getAdminAuditReport: (startupId: string, runId: string) =>
    request<AuditReport>(`/v1/admin/startups/${startupId}/audits/${runId}/report`),
  getAuditPdf: (startupId: string, runId: string) =>
    requestBytes(`/api/audits/${startupId}/${runId}/pdf`),

  listTasks: (startupId: string, query = "") =>
    request<Page<ReadinessTask>>(`/v1/startups/${startupId}/tasks${query}`),
  getTasksSummary: (startupId: string) =>
    request<ReadinessSummary>(`/v1/startups/${startupId}/tasks/summary`),
  getTask: (startupId: string, taskId: string) =>
    request<ReadinessTask>(`/v1/startups/${startupId}/tasks/${taskId}`),
  beginEvidence: (taskId: string, input: { filename: string; content_type: string }) =>
    request<{ evidence_id: string; upload_url: string; expires_in: number; max_bytes: number }>(
      `/v1/tasks/${taskId}/evidence`,
      { method: "POST", body: input },
    ),
  completeEvidence: (id: string) =>
    request<unknown>(`/v1/evidence/${id}/complete`, { method: "POST" }),
  listEvidence: (taskId: string) =>
    request<Page<{ id: string; filename: string; outcome: string | null; reasons: string[] | null; status: string; created_at: string }>>(
      `/v1/tasks/${taskId}/evidence`,
    ),
  reopenTask: (taskId: string) =>
    request<ReadinessTask>(`/v1/admin/tasks/${taskId}/reopen`, { method: "POST" }),

  chatMentor: (startupId: string, message: string, history: { role: string; content: string }[]) =>
    request<{ reply: string; citations: { kind: string; ref: string }[] }>(
      `/v1/startups/${startupId}/mentor/chat`,
      { method: "POST", body: { message, history } },
    ),
  chatMentorStream: (
    startupId: string,
    message: string,
    history: { role: string; content: string }[],
    onDelta: (text: string) => void,
  ) =>
    requestStream(
      `/v1/startups/${startupId}/mentor/chat/stream`,
      { message, history },
      (event, data) => {
        if (event === "delta" && typeof data.text === "string") onDelta(data.text);
      },
    ).then((done) => ({
      reply: typeof done.reply === "string" ? done.reply : "",
      citations: Array.isArray(done.citations)
        ? (done.citations as { kind: string; ref: string }[])
        : [],
    })),

  getInvestorMe: () => request<InvestorProfile>("/v1/investor/me"),
  putInvestorMe: (body: Record<string, unknown>) =>
    request<InvestorProfile>("/v1/investor/me", { method: "PUT", body }),
  listInvestorTheses: (qs = "") =>
    request<Page<InvestorReviewCard>>(`/v1/admin/investors${qs}`),
  decideThesisReview: (userId: string, accept: boolean) =>
    request<InvestorReviewCard>(`/v1/admin/investors/${userId}/thesis-review`, {
      method: "POST",
      body: { accept },
    }),
  discover: (qs: string) => request<Page<StartupCard>>(`/v1/discover${qs}`),
  discoverOne: (id: string) => request<StartupCard>(`/v1/discover/${id}`),
  chatAnalyst: (id: string, message: string, history: { role: string; content: string }[]) =>
    request<{ reply: string; citations: { kind: string; ref: string }[] }>(
      `/v1/discover/${id}/analyst/chat`,
      { method: "POST", body: { message, history } },
    ),
  getWatchlist: () => request<{ startup_ids: string[] }>("/v1/watchlist"),
  toggleWatch: (id: string) =>
    request<{ startup_ids: string[]; watching?: boolean }>(`/v1/watchlist/${id}`, {
      method: "POST",
    }),
  expressInterest: (id: string, note?: string) =>
    request<Interest>(`/v1/discover/${id}/interest`, {
      method: "POST",
      body: { note: note || null },
    }),
  listInterests: (status?: string) =>
    request<Interest[]>(`/v1/interests${status ? `?status=${status}` : ""}`),
  withdrawInterest: (id: string) =>
    request<Interest>(`/v1/interests/${id}/withdraw`, { method: "POST" }),
  approveInterest: (id: string) =>
    request<Interest>(`/v1/admin/interests/${id}/approve`, { method: "POST" }),
  declineInterest: (id: string) =>
    request<Interest>(`/v1/admin/interests/${id}/decline`, { method: "POST" }),
  revealInterest: (id: string) =>
    request<{ interest_id: string; audit_run_id: string; revealed_at: string }>(
      `/v1/admin/interests/${id}/reveal`,
      { method: "POST" },
    ),
  getRevealedReport: (interestId: string, runId: string) =>
    request<AuditReport>(`/v1/interests/${interestId}/reports/${runId}`),
  scheduleMeeting: (
    interestId: string,
    body: { scheduled_at: string; duration_minutes: number; location?: string; notes?: string },
  ) =>
    request<Meeting>(`/v1/admin/interests/${interestId}/meetings`, {
      method: "POST",
      body,
    }),
  proposeMeeting: (
    interestId: string,
    body: { scheduled_at: string; duration_minutes?: number; message?: string },
  ) =>
    request<Meeting>(`/v1/interests/${interestId}/meetings/propose`, {
      method: "POST",
      body,
    }),
  confirmMeeting: (
    interestId: string,
    meetingId: string,
    body: { scheduled_at?: string; duration_minutes?: number; location?: string; notes?: string } = {},
  ) =>
    request<Meeting>(`/v1/admin/interests/${interestId}/meetings/${meetingId}/confirm`, {
      method: "POST",
      body,
    }),
  listMeetings: (interestId: string) =>
    request<Meeting[]>(`/v1/interests/${interestId}/meetings`),
  listMyMeetings: () => request<Meeting[]>("/v1/me/meetings"),

  checkout: () =>
    request<{ checkout_url: string; session_id: string }>("/v1/billing/checkout", {
      method: "POST",
    }),
  getUnlock: () => request<unknown>("/v1/billing/unlock"),
  listProducts: (qs = "") => request<Page<Product>>(`/v1/products${qs}`),
  getProduct: (id: string) => request<Product>(`/v1/products/${id}`),
  createProduct: (body: Record<string, unknown>) =>
    request<Product>("/v1/admin/products", { method: "POST", body }),
  updateProduct: (id: string, body: Record<string, unknown>) =>
    request<Product>(`/v1/admin/products/${id}`, { method: "PATCH", body }),
  enrol: (id: string) =>
    request<{ status: string; checkout_url?: string | null }>(`/v1/products/${id}/enrol`, {
      method: "POST",
    }),
  listEnrolments: () => request<Page<Enrolment>>("/v1/me/enrolments"),

  listRecommendations: (startupId: string) =>
    request<Page<Product>>(`/v1/startups/${startupId}/recommendations`),

  listNotifications: () =>
    request<Page<NotificationItem>>("/v1/notifications"),
  markRead: (ids: string[]) =>
    request<Page<NotificationItem>>("/v1/notifications/read", {
      method: "POST",
      body: { ids },
    }).then(() => undefined),

  adminStats: () => request<AdminStats>("/v1/admin/stats"),
  exportCorpus: (qs = "") => request<CorpusPage>(`/v1/admin/corpus${qs}`),
  listUsers: (qs = "") => request<Page<UserRow>>(`/v1/admin/users${qs}`),
  provisionAdmin: (email: string, password: string) =>
    request<UserRow>("/v1/admin/users", { method: "POST", body: { email, password } }),
  suspendUser: (id: string) =>
    request<UserRow>(`/v1/admin/users/${id}/suspend`, { method: "POST" }),
  reactivateUser: (id: string) =>
    request<UserRow>(`/v1/admin/users/${id}/reactivate`, { method: "POST" }),
  changeRole: (id: string, role: string) =>
    request<UserRow>(`/v1/admin/users/${id}/role`, { method: "PATCH", body: { role } }),
  listStartups: (qs = "") => request<Page<ProfileResponse>>(`/v1/admin/startups${qs}`),

  listBenchmarks: (qs = "") => request<Benchmark[]>(`/v1/benchmarks${qs}`),
  getBenchmark: (id: string) => request<Benchmark>(`/v1/benchmarks/${id}`),
  createBenchmark: (body: Record<string, unknown>) =>
    request<Benchmark>("/v1/benchmarks", { method: "POST", body }),
  updateBenchmark: (id: string, body: Record<string, unknown>) =>
    request<Benchmark>(`/v1/benchmarks/${id}`, { method: "PATCH", body }),
  retireBenchmark: (id: string) =>
    request<Benchmark>(`/v1/benchmarks/${id}/retire`, { method: "POST" }),
};

export async function putFile(url: string, file: File) {
  const res = await fetch(url, { method: "PUT", body: file, headers: { "Content-Type": file.type } });
  if (!res.ok) throw new Error("Upload to storage failed.");
}
