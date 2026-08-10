/** Readiness tasks, evidence, and documents — wired to live `/v1` endpoints. */

export type DocumentKind =
  | 'deck'
  | 'financials'
  | 'cap_table'
  | 'registration_certificate'
  | 'other';

export type DocumentStatus = 'pending' | 'ready' | 'rejected';
export type ScanStatus = 'pending' | 'clean' | 'infected' | 'skipped';

export type StartupDocument = {
  id: string;
  startupId: string;
  kind: DocumentKind;
  filename: string;
  contentType: string | null;
  sizeBytes: number | null;
  status: DocumentStatus;
  scanStatus: ScanStatus;
  createdAt: string;
  updatedAt: string;
};

export type UploadTicket = {
  documentId: string;
  uploadUrl: string;
  expiresIn: number;
  maxBytes: number;
};

export type RegistryEntry = {
  country: string;
  countryName: string;
  registrar: string;
  shortName: string;
  documentName: string;
  numberLabel: string;
  numberExample: string;
};

export type TaskStatus = 'open' | 'submitted' | 'passed' | 'failed' | 'needs_more' | 'obsolete';
export type TaskRequirement = 'required' | 'recommended';

export type ReadinessTask = {
  id: string;
  startupId: string;
  auditRunId: string | null;
  dimension: string;
  action: string;
  requirement: TaskRequirement;
  status: TaskStatus;
  dimensionScore: number | null;
  isPriority: boolean;
  assessmentAttempts: number;
  attemptsRemaining: number;
  createdAt: string;
  updatedAt: string;
};

export type ReadinessSummary = {
  total: number;
  requiredTotal: number;
  requiredOpen: number;
  requiredPassed: number;
  recommendedTotal: number;
  hasAudit: boolean;
  gateCleared: boolean;
  discoverable: boolean;
};

export type EvidenceStatus = 'pending' | 'ready' | 'rejected';
export type AssessmentOutcome = 'pass' | 'fail' | 'needs_more';

export type EvidenceSubmission = {
  id: string;
  taskId: string;
  filename: string;
  contentType: string | null;
  sizeBytes: number | null;
  status: EvidenceStatus;
  outcome: AssessmentOutcome | null;
  reasons: string[] | null;
  assessedAt: string | null;
  errorCode: string | null;
  createdAt: string;
};

export type EvidenceUploadTicket = {
  evidenceId: string;
  uploadUrl: string;
  expiresIn: number;
  maxBytes: number;
};
