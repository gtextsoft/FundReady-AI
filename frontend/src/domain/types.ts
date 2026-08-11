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

/**
 * Stages a founder can pick. Matches the server enum (no Bootstrapped —
 * that posture is not a funding stage and could not be persisted).
 */
export const FOUNDER_STAGES = ['Pre-seed', 'Seed', 'Series A', 'Growth'] as const;

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
 * Direction of the cost to serve one more customer.
 *
 * Three choices rather than a free-text box, even though the server stores it
 * as text: the direction is the whole signal, and a fixed set is something an
 * audit can compare across submissions.
 */
export const COST_TRENDS = ['Falling', 'Flat', 'Rising'] as const;
export type CostTrend = '' | (typeof COST_TRENDS)[number];

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

  // -- Registration --------------------------------------------------------
  // Collected on the company-verification screen rather than in the
  // assessment, because that screen already asks most of it. They live on the
  // profile because that is where the server stores them.
  /** Registered legal name, exactly as on the certificate. */
  legalName: string;
  registrationNumber: string;
  /** The body it is registered with — CAC, Companies House, and so on. */
  registrar: string;
  /** Year of incorporation, which can differ from when trading started. */
  incorporationYear: string;
  /** Licences the model requires, and whether they are held. */
  regulatoryLicences: string;

  // -- Market and plan -----------------------------------------------------
  /** The reachable market, and how the founder arrived at it. */
  marketSize: string;
  /** Who else solves this for their customers today. */
  competition: string;
  /** The one thing holding growth back right now. */
  growthConstraint: string;
  /** What new capital buys, mapped to the constraint above. */
  useOfFunds: string;

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
  /** Monthly sales and marketing spend, salaries included. */
  marketingSpend: string;

  // -- Customers -----------------------------------------------------------
  customers: string;
  /** Average revenue per customer per month. Half of lifetime value. */
  arpu: string;
  /** Monthly churn, as a percentage. The other half. */
  churn: string;
  cac: string;
  /** Monthly active users, for businesses that count them separately. */
  activeUsers: string;
  /** Signed pilots or letters of intent that are not paying yet. */
  pilots: string;
  /** Share of revenue from the biggest customer — concentration risk. */
  customerConcentration: string;
  /**
   * Whether the cost to serve one more customer is falling, flat or rising.
   * Free text on the server, but asked as three choices: the direction is what
   * matters, and a fixed set produces data an audit can actually compare.
   */
  deliveryCostTrend: CostTrend;

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
  /** Prior experience of the founders, specific enough to check. */
  founderExperience: string;
  /** Who owns what, in summary. */
  capTable: string;

  /** Filename of the uploaded deck, or '' when nothing is on file. */
  deck: string;
};

export const EMPTY_PROFILE: FounderProfile = {
  legalName: '',
  registrationNumber: '',
  registrar: '',
  incorporationYear: '',
  regulatoryLicences: '',
  marketSize: '',
  competition: '',
  growthConstraint: '',
  useOfFunds: '',
  marketingSpend: '',
  activeUsers: '',
  pilots: '',
  customerConcentration: '',
  deliveryCostTrend: '',
  founderExperience: '',
  capTable: '',
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
  investorType: InvestorType | string;
  firm: string;
  country: string;
  linkedinUrl: string;
};

/** Full investor thesis + firm profile (`GET/PUT /v1/investor/me`). */
export type InvestorProfile = {
  firm: string;
  investorType: string;
  country: string;
  linkedinUrl: string;
  thesisSectors: string[];
  thesisStages: string[];
  thesisGeographies: string[];
  ticketMinMinor: number | null;
  ticketMaxMinor: number | null;
  ticketCurrency: string | null;
  riskNotes: string;
  kycStatus: string;
};

export type KycSession = {
  url: string;
  sessionId: string;
  kycStatus: string;
};

export type CatalogueProduct = {
  id: string;
  kind: string;
  slug: string;
  title: string;
  description: string;
  regions: string[];
  gapTags: string[];
  amountMinor: number | null;
  currency: string | null;
  eventStartsAt: string | null;
  eventLocation: string | null;
  active: boolean;
};

export type Enrolment = {
  id: string;
  productId: string;
  createdAt: string;
  product: CatalogueProduct | null;
};

export type EnrolResult = {
  status: 'enrolled' | 'checkout_required';
  enrolment: Enrolment | null;
  checkoutUrl: string | null;
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
  /** ISO date from the server. Full access until this moment when unpaid. */
  trialEndsAt: string;
  /**
   * Whether access has been paid for. A status rather than a payment date,
   * because the server reports the subscription's state and not when it began.
   */
  subscriptionStatus: SubscriptionStatus;
  /**
   * Server-authoritative entitlement (`/v1/users/me.has_access`).
   * Prefer this over recomputing trial locally when present.
   */
  hasAccess?: boolean;
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
