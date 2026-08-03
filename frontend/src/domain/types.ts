export type MatchType = 'VC' | 'PE';

export const SECTORS = [
  'Fintech',
  'Healthtech',
  'SaaS / B2B',
  'Climate',
  'AI Infrastructure',
  'Marketplace',
] as const;

/** Onboarding offers two sectors the dealflow filters do not. */
export const ONBOARDING_SECTORS = [...SECTORS, 'Consumer', 'Deeptech'] as const;

export const STAGES = ['Pre-seed', 'Seed', 'Series A', 'Growth'] as const;

/** Founders may also self-describe as bootstrapped; listed companies may not. */
export const FOUNDER_STAGES = ['Pre-seed', 'Seed', 'Series A', 'Bootstrapped'] as const;

export type Sector = (typeof SECTORS)[number];
export type Stage = (typeof STAGES)[number];
export type FounderStage = (typeof FOUNDER_STAGES)[number];

export type TeamMember = { name: string; role: string; note: string };

export type RiskFlag = { color: string; title: string; body: string };

/** A company as an investor sees it in the dealflow database. */
export type Company = {
  id: number;
  name: string;
  sector: Sector;
  stage: Stage;
  tagline: string;
  location: string;
  score: number;
  /** Monthly recurring revenue, in whole dollars. */
  mrr: number;
  /** Month-over-month growth, in percent. */
  growth: number;
  /** Gross margin, in percent. */
  margin: number;
  ltvcac: number;
  /** Runway, in months. */
  runway: number;
  match: MatchType;
  /** Days since the company was listed — drives the "Newest" sort. */
  ageDays: number;
  founder: string;
  /** Six months of revenue, oldest first. */
  trend: number[];
  memoDate: string;
  responseTime: string;
  team: TeamMember[];
  memo1: string;
  memo2: string;
  fits: string[];
  flags: RiskFlag[];
};

export type RevModel = 'MRR' | 'ARR';

/** A yes/no the founder has not answered yet. */
export type YesNo = '' | 'Yes' | 'No';

/**
 * The founder onboarding form. Every field is a string because these are raw
 * text inputs — scoring parses them. An empty string means "not answered yet".
 *
 * **Every question here asks for something the founder knows, never something
 * the platform can work out.** Gross margin, lifetime value and market size
 * used to be asked directly; all three were removed (`docs/INTAKE.md`). The
 * server computes the first two from raw figures, and the audit rubric marks
 * down a market size quoted as a single unsourced number — so asking for one
 * handed the founder a way to score badly. Cost of revenue, ARPU and churn are
 * their replacements: smaller questions, and checkable.
 */
export type FounderProfile = {
  // -- About the company ---------------------------------------------------
  company: string;
  sector: string;
  location: string;
  year: string;
  stage: string;
  /** What the business does. Required before an audit can run. */
  description: string;
  /** How it makes money. Required before an audit can run. */
  businessModel: string;
  website: string;

  // -- Money ---------------------------------------------------------------
  /** Whether `revenue` is stated monthly or annually. A unit, not a figure. */
  revModel: RevModel;
  revenue: string;
  /** Total monthly costs. Required before an audit can run. */
  costs: string;
  /** Cost of delivering the revenue. The server derives gross margin from it. */
  costOfRevenue: string;
  /** Cash in the bank. Required before an audit can run — it sets runway. */
  cash: string;
  totalRaised: string;
  raiseTarget: string;

  // -- Customers -----------------------------------------------------------
  customers: string;
  /** Average revenue per customer per month. Half of lifetime value. */
  arpu: string;
  /** Monthly churn, as a percentage. The other half. */
  churn: string;
  cac: string;

  // -- Team and ownership --------------------------------------------------
  founders: string;
  foundersFullTime: string;
  /** Everyone, not just founders. Required before an audit can run. */
  teamSize: string;
  /** Whether the company owns what its people built. */
  ipOwned: YesNo;
  /** Whether customer contracts survive a change of owner. */
  contractsTransferable: YesNo;
  /** What only the founder can currently do. */
  keyPersonDependency: string;

  /** Filename of the uploaded deck, or '' when nothing is on file. */
  deck: string;
};

export const EMPTY_PROFILE: FounderProfile = {
  company: '',
  sector: '',
  location: '',
  year: '',
  stage: '',
  description: '',
  businessModel: '',
  website: '',
  revModel: 'MRR',
  revenue: '',
  costs: '',
  costOfRevenue: '',
  cash: '',
  totalRaised: '',
  raiseTarget: '',
  customers: '',
  arpu: '',
  churn: '',
  cac: '',
  founders: '',
  foundersFullTime: '',
  teamSize: '',
  ipOwned: '',
  contractsTransferable: '',
  keyPersonDependency: '',
  deck: '',
};

/** One weighted component of the Fundability Score. */
export type ScorePart = { key: string; value: number; max: number };

export type Insight = { title: string; body: string };

export type Fit = 'High' | 'Moderate' | 'Low';

export type Assessment = {
  score: number;
  parts: ScorePart[];
  bandLabel: string;
  bandColor: string;
  vcFit: Fit;
  peFit: Fit;
  strengths: Insight[];
  risks: Insight[];
  /** Below 50 routes to Funding Readiness; 50 and above to Wealth Creation. */
  route: 'readiness' | 'wealth';
};

/**
 * Verification state. `in_review` exists because a real registry check is not
 * instant — the UI has to show a waiting state rather than pretend.
 */
export type VerificationStatus = 'unverified' | 'in_review' | 'verified' | 'rejected';

/** What a founder submits to prove the company is registered in its country. */
export type CompanyRegistration = {
  country: string;
  /** Registrar's company number, e.g. an RC number in Nigeria. */
  registrationNumber: string;
  /** The body the company is registered with, e.g. "CAC". */
  registrar: string;
  legalName: string;
  /** Filename of the uploaded certificate. */
  document: string;
};

export const INVESTOR_TYPES = [
  'Angel investor',
  'Venture capital',
  'Private equity',
  'Family office',
  'Corporate / strategic',
] as const;

export type InvestorType = (typeof INVESTOR_TYPES)[number];

/** Deliberately light-touch — enough to establish who someone is, no more. */
export type InvestorCredentials = {
  investorType: InvestorType;
  firm: string;
  country: string;
  linkedinUrl: string;
};

/**
 * Founder billing state. Mirrors the server's `subscription_status`, which is
 * trusted from Stripe webhooks only — never from anything the client reports.
 */
export type SubscriptionStatus = 'none' | 'active' | 'past_due' | 'canceled';

/**
 * Whether the address on the account has been confirmed.
 *
 * Distinct from every other verification in this app: it proves the person
 * controls the mailbox, and it gates the sensitive actions (buying, uploading,
 * being discovered) per AUTH.md. Company registration and investor credentials
 * are separate, later checks.
 */
export type EmailVerification = { emailVerified: boolean };

export type FounderAccount = EmailVerification & {
  companyName: string;
  verification: VerificationStatus;
  registration: CompanyRegistration | null;
  /** ISO date. Full access until this moment, then the paywall applies. */
  trialEndsAt: string;
  /**
   * Whether access has been paid for. A status rather than a payment date,
   * because the server reports the subscription's state and not when it began.
   */
  subscriptionStatus: SubscriptionStatus;
};

export type InvestorAccount = EmailVerification & {
  verification: VerificationStatus;
  credentials: InvestorCredentials | null;
};

export type SortKey = 'score' | 'scoreAsc' | 'new' | 'rev';

export type DealflowQuery = {
  query: string;
  minScore: number;
  match: 'All' | MatchType;
  sectors: string[];
  stages: string[];
  sort: SortKey;
  /** When set, restrict results to these company ids (watchlist view). */
  ids?: number[];
};
