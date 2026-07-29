import { COMPANIES, companyById } from '@/domain/companies';
import { TRIAL_DAYS } from '@/domain/access';
import type { AppNotification, CallRequest, NotificationKind } from '@/domain/notifications';
import { UNLOCK_PRICE } from '@/domain/pricing';
import { assess } from '@/domain/scoring';
import type {
  Assessment,
  Company,
  CompanyRegistration,
  DealflowQuery,
  FounderAccount,
  FounderProfile,
  InvestorAccount,
  InvestorCredentials,
} from '@/domain/types';
import { isPersonalEmailDomain } from '@/domain/email';
import type {
  CompanySummary,
  Credentials,
  DomainLookup,
  FundMeApi,
  Page,
  PaymentReceipt,
  Role,
  Session,
} from './contract';

/**
 * Stand-in backend. Everything lives in module memory and resets on reload.
 *
 * It is deliberately stateful across sign-outs: the notification log and call
 * requests survive, so you can request a call as an investor, sign out, sign
 * up as a founder and find the request waiting — the demo of the whole loop.
 */

const delay = (ms: number) => new Promise<void>((r) => setTimeout(r, ms));
const iso = (offsetMs = 0) => new Date(Date.now() + offsetMs).toISOString();
const id = (prefix: string) => `${prefix}_${Math.random().toString(36).slice(2, 9)}`;

const DAY = 86_400_000;

/** How long the mock pretends a registry check takes. */
const REVIEW_MS = 6000;

/**
 * Domains whose company runs single sign-on. In production this is a directory
 * the backend owns, keyed by verified domain; here one entry exists so the
 * flow can be exercised.
 */
const SSO_DOMAINS: Record<string, { provider: string; displayName: string }> = {
  'acmecorp.com': { provider: 'okta', displayName: 'Okta' },
};

let watchlist: number[] = [3, 5];
let savedProfile: FounderProfile | null = null;
let notifications: AppNotification[] = [];
let callRequests: CallRequest[] = [];

let founderAccount: FounderAccount = {
  companyName: '',
  verification: 'unverified',
  registration: null,
  trialEndsAt: iso(TRIAL_DAYS * DAY),
  paidAt: null,
};

let investorAccount: InvestorAccount = {
  verification: 'unverified',
  credentials: null,
};

function notify(
  audience: Role,
  kind: NotificationKind,
  title: string,
  body: string,
  extra: Partial<AppNotification> = {},
): AppNotification {
  const n: AppNotification = {
    id: id('n'),
    audience,
    kind,
    title,
    body,
    createdAt: iso(),
    read: false,
    ...extra,
  };
  notifications = [n, ...notifications];
  return n;
}

/** A couple of investor-side alerts so the tab is not empty on first run. */
function seedInvestorAlerts() {
  if (notifications.some((n) => n.audience === 'investor' && n.kind === 'score_changed')) return;
  const tessellate = companyById(3);
  if (tessellate) {
    notify(
      'investor',
      'score_changed',
      `${tessellate.name} moved to ${tessellate.score}`,
      'Fundability score rose 4 points after an updated revenue submission.',
      { companyId: tessellate.id, createdAt: iso(-2 * 3600_000), read: true },
    );
  }
  notify(
    'investor',
    'new_matches',
    '3 new companies match your mandate',
    'Fintech and AI Infrastructure at Seed, scoring 75 and above.',
    { createdAt: iso(-2 * DAY), read: true },
  );
}

function session(email: string, role: Role): Session {
  const handle = email.split('@')[0] || 'there';
  return {
    token: `mock.${Math.random().toString(36).slice(2)}`,
    userId: `u_${handle}`,
    email,
    role,
    displayName: handle.replace(/[._-]+/g, ' ').replace(/\b\w/g, (m) => m.toUpperCase()),
  };
}

function toSummary(c: Company): CompanySummary {
  return {
    id: c.id, name: c.name, tagline: c.tagline, sector: c.sector,
    stage: c.stage, score: c.score, mrr: c.mrr, growth: c.growth, match: c.match,
  };
}

const SORTS: Record<DealflowQuery['sort'], (a: Company, b: Company) => number> = {
  score: (a, b) => b.score - a.score,
  scoreAsc: (a, b) => a.score - b.score,
  new: (a, b) => a.ageDays - b.ageDays,
  rev: (a, b) => b.mrr - a.mrr,
};

export function filterCompanies(q: DealflowQuery): Company[] {
  const needle = q.query.trim().toLowerCase();
  const matched = COMPANIES.filter((c) => {
    if (q.ids && !q.ids.includes(c.id)) return false;
    if (c.score < q.minScore) return false;
    if (q.match !== 'All' && c.match !== q.match) return false;
    if (q.sectors.length && !q.sectors.includes(c.sector)) return false;
    if (q.stages.length && !q.stages.includes(c.stage)) return false;
    if (needle && !`${c.name} ${c.tagline} ${c.sector} ${c.founder}`.toLowerCase().includes(needle)) return false;
    return true;
  });
  return [...matched].sort(SORTS[q.sort]);
}

/**
 * Stand-in for the AI mentor.
 *
 * Deliberately rule-based over the founder's own numbers rather than canned
 * filler — the answers are true, just not generated. Swap the whole function
 * for an LLM call behind `askMentor` when the backend is ready.
 */
function mentorAnswer(question: string, profile: FounderProfile | null): string {
  if (!profile) {
    return 'Run your Fundability assessment first — once I can see your revenue, growth and unit economics I can give you a specific answer rather than a generic one.';
  }

  const q = question.toLowerCase();
  const a = assess(profile);
  const n = (v: string) => parseFloat(String(v).replace(/[^0-9.\-]/g, '')) || 0;
  const ratio = n(profile.cac) > 0 ? n(profile.ltv) / n(profile.cac) : 0;

  if (/growth|grow|traction|mom/.test(q)) {
    const g = n(profile.growth);
    return g >= 15
      ? `You are compounding at ${g}% month over month, which is top-decile at ${profile.stage || 'your stage'}. The question investors will ask next is durability: show them two quarters of cohort retention so the rate does not read as a launch spike.`
      : `At ${g}% MoM you are below the 8–15% band most seed funds screen on. The fastest lever is usually channel concentration — find the single channel with the best payback and put everything behind it for a quarter, rather than spreading across three.`;
  }

  if (/cac|ltv|payback|unit econ/.test(q)) {
    return ratio >= 3
      ? `Your LTV:CAC is ${ratio.toFixed(1)}:1, which clears the 3:1 institutional bar. Expect diligence on channel mix — a strong blended figure is usually carried by one channel. Bring cohort-level attribution.`
      : ratio > 0
        ? `Your LTV:CAC is ${ratio.toFixed(1)}:1. Below 3:1 an investor reads it as spending more to acquire than you get back. Either lift LTV through expansion revenue, or cut CAC by dropping your worst-performing channel.`
        : 'You have not given me CAC and LTV yet. Missing unit economics is the single most common reason for a pass — add them in the assessment and I can tell you where you stand.';
  }

  if (/margin/.test(q)) {
    const m = n(profile.margin);
    return m >= 70
      ? `${m}% gross margin is software-grade — it means incremental revenue drops through instead of funding delivery. Lead with this in your deck.`
      : `${m}% gross margin caps how far each dollar of revenue travels. Identify which cost line sits in COGS and whether it is structural or just unoptimised — that answer changes whether you look VC-shaped or PE-shaped.`;
  }

  if (/tam|market/.test(q)) {
    const t = n(profile.tam);
    return t >= 5
      ? `A $${t}B TAM leaves room for a venture-scale outcome. Be ready to defend how you sized it — bottom-up beats a analyst top-down number every time.`
      : `A $${t}B TAM is tight for venture. That is not fatal, but it points at a PE-style path — profitable compounding rather than a step change. Your PE-fit is currently ${a.peFit}.`;
  }

  if (/deck|document|pitch/.test(q)) {
    return profile.deck
      ? `Your deck is on file. The highest-leverage edit is usually slide two: state the metric that is compounding, not the mission. Yours is ${n(profile.growth)}% MoM.`
      : 'You have no deck on file. Investors cannot progress without one — that is the single highest-leverage fix on your list right now.';
  }

  if (/score|fundability|improve|raise/.test(q)) {
    const weakest = [...a.parts].sort((x, y) => x.value / x.max - y.value / y.max)[0];
    return `You are at ${a.score}/100 — ${a.bandLabel.toLowerCase()}. Your weakest component is ${weakest.key} at ${Math.round(weakest.value)}/${weakest.max}, so that is where a point of effort buys the most score. Your VC-fit is ${a.vcFit} and PE-fit is ${a.peFit}.`;
  }

  if (/investor|vc|pe|raise|fund/.test(q)) {
    return a.vcFit === 'High'
      ? `Your profile reads venture-shaped — VC-fit ${a.vcFit}. Target funds whose mandate matches ${profile.sector || 'your sector'} at ${profile.stage || 'your stage'}, and lead with growth rate over TAM.`
      : `Your VC-fit is ${a.vcFit} and PE-fit is ${a.peFit}. Do not spray venture funds; a PE or growth-equity conversation will value what you actually have, which is ${n(profile.margin)}% margin on a real revenue base.`;
  }

  const topRisk = a.risks[0];
  return `The thing I would fix first is "${topRisk.title}" — ${topRisk.body} You are at ${a.score}/100 overall. Ask me about growth, unit economics, margin, TAM or your deck for something more specific.`;
}

/** Accounts created this session: email → role. Cleared on reload. */
const knownAccounts = new Map<string, Role>();

/**
 * Which side a login lands on.
 *
 * A real backend reads the role off the stored account; the mock has to guess
 * for addresses it never saw signed up, so that both sides stay reachable from
 * the login screen after a reload. The load-bearing rule is the first one: a
 * founder account cannot exist on a consumer mailbox domain, so a personal
 * address must never resolve to the founder side. Without it, signing in as
 * `you@gmail.com` would walk straight past the company-domain requirement.
 */
function roleForSignIn(email: string): Role {
  const known = knownAccounts.get(email.trim().toLowerCase());
  if (known) return known;

  if (isPersonalEmailDomain(email.split('@')[1] ?? '')) return 'investor';
  return /invest|vc|capital|partners|fund/i.test(email) ? 'investor' : 'founder';
}

/**
 * Test seam: lets the profile screen's developer controls move the trial
 * boundary so both sides of the paywall can be demonstrated without waiting
 * two weeks. Delete along with the mock.
 */
export function __setTrialEndsAt(isoDate: string) {
  founderAccount = { ...founderAccount, trialEndsAt: isoDate };
}

export const mockApi: FundMeApi = {
  async signIn({ email }: Credentials) {
    await delay(450);
    const role = roleForSignIn(email);
    if (role === 'investor') seedInvestorAlerts();
    return session(email, role);
  },

  async signUp({ email, role }) {
    await delay(600);
    // The client blocks this too, but the server is the authority — a client
    // check is a convenience, never a control.
    if (role === 'founder' && isPersonalEmailDomain(email.split('@')[1] ?? '')) {
      throw new Error('personal_email_domain');
    }
    knownAccounts.set(email.trim().toLowerCase(), role);
    if (role === 'founder') {
      founderAccount = {
        companyName: '',
        verification: 'unverified',
        registration: null,
        trialEndsAt: iso(TRIAL_DAYS * DAY),
        paidAt: null,
      };
    } else {
      investorAccount = { verification: 'unverified', credentials: null };
      seedInvestorAlerts();
    }
    return session(email, role);
  },

  async lookupEmailDomain(domain: string): Promise<DomainLookup> {
    await delay(350);
    const d = domain.trim().toLowerCase();
    return {
      domain: d,
      personal: isPersonalEmailDomain(d),
      // Stand-in for a real directory lookup. Only `acmecorp.com` is wired, so
      // the SSO path can be demonstrated without inventing it for everyone.
      sso: SSO_DOMAINS[d] ?? null,
    };
  },

  async signInWithSso(domain: string, role: Role) {
    await delay(900);
    knownAccounts.set(`founder@${domain}`.toLowerCase(), role);
    if (role === 'investor') seedInvestorAlerts();
    if (role === 'founder') {
      founderAccount = {
        companyName: '',
        verification: 'unverified',
        registration: null,
        trialEndsAt: iso(TRIAL_DAYS * DAY),
        paidAt: null,
      };
    }
    return session(`founder@${domain}`, role);
  },

  async signOut() {
    await delay(120);
  },

  async requestPasswordReset() {
    await delay(700);
  },

  async getFounderAccount() {
    await delay(120);
    return { ...founderAccount };
  },

  async getInvestorAccount() {
    await delay(120);
    return { ...investorAccount };
  },

  async submitCompanyRegistration(registration: CompanyRegistration) {
    await delay(700);
    founderAccount = { ...founderAccount, registration, verification: 'in_review' };

    // A registry check is not instant. Approve on a timer so the app has to
    // handle the waiting state honestly rather than flipping straight to done.
    setTimeout(() => {
      founderAccount = { ...founderAccount, verification: 'verified' };
      notify(
        'founder',
        'verification_approved',
        'Company verified',
        `${registration.legalName} was confirmed as registered with ${registration.registrar} in ${registration.country}. You are now visible to investors.`,
      );
    }, REVIEW_MS);

    return { ...founderAccount };
  },

  async submitInvestorCredentials(credentials: InvestorCredentials) {
    await delay(650);
    // Deliberately light-touch: confirm who they are and let them through.
    investorAccount = { ...investorAccount, credentials, verification: 'verified' };
    notify(
      'investor',
      'verification_approved',
      'Investor profile verified',
      `${credentials.firm} confirmed. You can now request introductions and schedule calls.`,
    );
    return { ...investorAccount };
  },

  async purchaseUnlock(): Promise<PaymentReceipt> {
    await delay(1400);
    const paidAt = iso();
    founderAccount = { ...founderAccount, paidAt };
    const receipt: PaymentReceipt = {
      reference: id('pay').toUpperCase(),
      amount: UNLOCK_PRICE.amount,
      currency: UNLOCK_PRICE.currency,
      paidAt,
    };
    notify(
      'founder',
      'payment_receipt',
      'Payment received',
      `${UNLOCK_PRICE.label} one-off unlock confirmed. Reference ${receipt.reference}.`,
    );
    return receipt;
  },

  async submitAssessment(profile: FounderProfile): Promise<Assessment> {
    await delay(300);
    savedProfile = profile;
    founderAccount = { ...founderAccount, companyName: profile.company };
    return assess(profile);
  },

  async getProfile() {
    await delay(120);
    return savedProfile;
  },

  async enrol() {
    await delay(400);
  },

  async askMentor(question: string) {
    await delay(900);
    return mentorAnswer(question, savedProfile);
  },

  async listCompanies(query, page, perPage): Promise<Page<CompanySummary>> {
    await delay(220);
    const all = filterCompanies(query);
    const pages = Math.max(1, Math.ceil(all.length / perPage));
    const safePage = Math.min(Math.max(1, page), pages);
    return {
      rows: all.slice((safePage - 1) * perPage, safePage * perPage).map(toSummary),
      total: all.length,
      page: safePage,
      perPage,
    };
  },

  async getCompany(id: number) {
    await delay(180);
    const c = companyById(id);
    if (!c) throw new Error(`No company with id ${id}`);
    return c;
  },

  async getWatchlist() {
    await delay(80);
    return [...watchlist];
  },

  async toggleWatch(companyId: number) {
    await delay(80);
    watchlist = watchlist.includes(companyId)
      ? watchlist.filter((x) => x !== companyId)
      : [...watchlist, companyId];
    return [...watchlist];
  },

  async requestIntroduction(companyId: number) {
    await delay(650);
    const company = companyById(companyId);
    notify(
      'founder',
      'intro_requested',
      'An investor requested an introduction',
      `${investorAccount.credentials?.firm ?? 'An investor'} asked to be introduced to ${company?.name ?? 'your company'}.`,
      { companyId },
    );
  },

  async requestCall({ companyId, proposedAt, durationMinutes, note }) {
    await delay(700);
    const company = companyById(companyId);
    const request: CallRequest = {
      id: id('call'),
      companyId,
      companyName: company?.name ?? 'Your company',
      investorName: investorAccount.credentials ? 'Investor' : 'An investor',
      investorFirm: investorAccount.credentials?.firm ?? 'Independent',
      proposedAt,
      durationMinutes,
      note,
      status: 'pending',
    };
    callRequests = [request, ...callRequests];

    notify(
      'founder',
      'call_requested',
      `${request.investorFirm} requested a virtual call`,
      note || `A ${durationMinutes}-minute introductory call about ${request.companyName}.`,
      { companyId, callRequestId: request.id },
    );

    return { ...request };
  },

  async listCallRequests() {
    await delay(150);
    return callRequests.map((r) => ({ ...r }));
  },

  async respondToCall(requestId: string, accept: boolean) {
    await delay(400);
    const request = callRequests.find((r) => r.id === requestId);
    if (!request) throw new Error(`No call request ${requestId}`);
    request.status = accept ? 'accepted' : 'declined';

    notify(
      'investor',
      accept ? 'call_accepted' : 'call_declined',
      accept
        ? `${request.companyName} accepted your call`
        : `${request.companyName} declined your call`,
      accept
        ? 'The slot is confirmed. A calendar invitation is on its way.'
        : 'They passed on this slot. You can propose another time.',
      { companyId: request.companyId },
    );

    return { ...request };
  },

  async listNotifications(audience: Role) {
    await delay(120);
    return notifications.filter((n) => n.audience === audience).map((n) => ({ ...n }));
  },

  async markNotificationsRead(ids: string[]) {
    await delay(60);
    const set = new Set(ids);
    notifications = notifications.map((n) => (set.has(n.id) ? { ...n, read: true } : n));
  },
};
