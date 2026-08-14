import { CODE_TO_COUNTRY, COUNTRY_TO_CODE, STAGE_TO_WIRE, WIRE_TO_STAGE } from "./email";

export type FounderForm = {
  company: string;
  sector: string;
  location: string;
  year: string;
  stage: string;
  description: string;
  businessModel: string;
  website: string;
  revenue: string;
  costs: string;
  costOfRevenue: string;
  cash: string;
  revenue12m: string;
  revenue3mAgo: string;
  costs3mAgo: string;
  marketingSpend: string;
  totalRaised: string;
  raiseTarget: string;
  founderSalary: string;
  capitalMix: string;
  customers: string;
  mau: string;
  arpu: string;
  churn: string;
  cac: string;
  pilots: string;
  largestCustomerShare: string;
  teamSize: string;
  founders: string;
  foundersFullTime: string;
  marketSize: string;
  competition: string;
  growthConstraint: string;
  useOfFunds: string;
  deliveryCostTrend: string;
  capTable: string;
  founderExperience: string;
  keyPerson: string;
  hiringGaps: string;
  ipOwned: string;
  contractsTransferable: string;
  operationsDocumented: string;
  systemsInCompanyName: string;
  supplierDependencies: string;
  channelDependency: string;
  recurringRevenue: string;
  typicalContractMonths: string;
  materialContracts: string;
  legalName: string;
  registrationNumber: string;
  registrar: string;
  incorporationYear: string;
  licences: string;
  tradedBeforeIncorporation: string;
  taxFiling: string;
  fxExposure: string;
  localContent: string;
};

export const EMPTY_FORM: FounderForm = {
  company: "",
  sector: "",
  location: "",
  year: "",
  stage: "",
  description: "",
  businessModel: "",
  website: "",
  revenue: "",
  costs: "",
  costOfRevenue: "",
  cash: "",
  revenue12m: "",
  revenue3mAgo: "",
  costs3mAgo: "",
  marketingSpend: "",
  totalRaised: "",
  raiseTarget: "",
  founderSalary: "",
  capitalMix: "",
  customers: "",
  mau: "",
  arpu: "",
  churn: "",
  cac: "",
  pilots: "",
  largestCustomerShare: "",
  teamSize: "",
  founders: "",
  foundersFullTime: "",
  marketSize: "",
  competition: "",
  growthConstraint: "",
  useOfFunds: "",
  deliveryCostTrend: "",
  capTable: "",
  founderExperience: "",
  keyPerson: "",
  hiringGaps: "",
  ipOwned: "",
  contractsTransferable: "",
  operationsDocumented: "",
  systemsInCompanyName: "",
  supplierDependencies: "",
  channelDependency: "",
  recurringRevenue: "",
  typicalContractMonths: "",
  materialContracts: "",
  legalName: "",
  registrationNumber: "",
  registrar: "",
  incorporationYear: "",
  licences: "",
  tradedBeforeIncorporation: "",
  taxFiling: "",
  fxExposure: "",
  localContent: "",
};

export const ONBOARDING_STEPS = [
  "Company",
  "Legal",
  "Money",
  "Customers",
  "Market",
  "Team",
  "Ownership",
] as const;

export const STEP_REQUIRED: Record<number, (keyof FounderForm)[]> = {
  0: ["company", "sector", "location", "description", "businessModel"],
  1: [],
  2: ["stage", "revenue", "costs", "cash"],
  3: [],
  4: ["marketSize"],
  5: ["founders", "teamSize"],
  6: [],
};

export const FIELD_LABELS: Partial<Record<keyof FounderForm, string>> = {
  company: "Company name",
  sector: "Sector",
  location: "Country",
  description: "What the business does",
  businessModel: "How it makes money",
  stage: "Stage",
  revenue: "Monthly revenue",
  costs: "Monthly costs",
  cash: "Cash on hand",
  marketSize: "Reachable market",
  founders: "Founders",
  teamSize: "Team size",
};

export const AUDIT_READY_TOTAL = 11;

function n(v: string) {
  const t = v.trim().replace(/[, ]/g, "");
  if (!t) return null;
  const p = Number(t);
  return Number.isFinite(p) ? p : null;
}

function field(value: string | number | boolean) {
  return { value, source: "founder" as const };
}

function textOf(value: unknown): string {
  if (typeof value === "string") return value;
  if (value == null) return "";
  return String(value);
}

function numOf(value: unknown): string {
  if (typeof value === "number" && Number.isFinite(value)) return String(value);
  return "";
}

function majorOf(value: unknown): string {
  if (typeof value !== "number" || !Number.isFinite(value)) return "";
  return String(value / 100);
}

function ynOf(value: unknown): string {
  if (value === true) return "Yes";
  if (value === false) return "No";
  return "";
}

type WireProfile = {
  name: string | null;
  sector: string | null;
  stage: string | null;
  country: string | null;
  fields: Record<string, { value: string | number | boolean | null }>;
};

export function fromWire(profile: WireProfile): FounderForm {
  const f = profile.fields ?? {};
  const v = (name: string) => f[name]?.value ?? null;
  return {
    ...EMPTY_FORM,
    company: profile.name ?? "",
    sector: profile.sector ?? "",
    location: CODE_TO_COUNTRY[profile.country ?? ""] ?? "",
    stage: WIRE_TO_STAGE[profile.stage ?? ""] ?? "",
    description: textOf(v("description")),
    businessModel: textOf(v("business_model")),
    website: textOf(v("website")),
    year: numOf(v("founded_year")),
    revenue: majorOf(v("monthly_revenue_minor")),
    costs: majorOf(v("monthly_costs_minor")),
    costOfRevenue: majorOf(v("cost_of_revenue_minor")),
    cash: majorOf(v("cash_on_hand_minor")),
    revenue12m: majorOf(v("last_12m_revenue_minor")),
    revenue3mAgo: majorOf(v("monthly_revenue_3m_ago_minor")),
    costs3mAgo: majorOf(v("monthly_costs_3m_ago_minor")),
    marketingSpend: majorOf(v("monthly_marketing_spend_minor")),
    totalRaised: majorOf(v("total_raised_minor")),
    raiseTarget: majorOf(v("current_raise_target_minor")),
    founderSalary: majorOf(v("founder_salary_minor")),
    capitalMix: textOf(v("capital_mix_note")),
    customers: numOf(v("active_customers")),
    mau: numOf(v("monthly_active_users")),
    arpu: majorOf(v("average_revenue_per_customer_minor")),
    churn: numOf(v("monthly_churn_percent")),
    cac: majorOf(v("customer_acquisition_cost_minor")),
    pilots: numOf(v("pilot_or_lou_count")),
    largestCustomerShare: numOf(v("largest_customer_revenue_share_percent")),
    teamSize: numOf(v("team_size")),
    founders: numOf(v("founder_count")),
    foundersFullTime: numOf(v("founders_full_time")),
    marketSize: textOf(v("market_size_note")),
    competition: textOf(v("competition_note")),
    growthConstraint: textOf(v("growth_constraint")),
    useOfFunds: textOf(v("use_of_funds")),
    deliveryCostTrend: textOf(v("delivery_cost_trend")),
    capTable: textOf(v("cap_table_summary")),
    founderExperience: textOf(v("founder_experience")),
    keyPerson: textOf(v("key_person_dependency")),
    hiringGaps: textOf(v("hiring_gaps")),
    ipOwned: ynOf(v("ip_owned")),
    contractsTransferable: ynOf(v("contracts_transferable")),
    operationsDocumented: ynOf(v("operations_documented")),
    systemsInCompanyName: ynOf(v("systems_in_company_name")),
    supplierDependencies: textOf(v("supplier_dependencies")),
    channelDependency: textOf(v("channel_dependency")),
    recurringRevenue: numOf(v("recurring_revenue_percent")),
    typicalContractMonths: numOf(v("typical_contract_months")),
    materialContracts: textOf(v("material_contracts_note")),
    legalName: textOf(v("legal_name")),
    registrationNumber: textOf(v("registration_number")),
    registrar: textOf(v("registrar")),
    incorporationYear: numOf(v("incorporation_year")),
    licences: textOf(v("regulatory_licences")),
    tradedBeforeIncorporation: ynOf(v("trading_before_incorporation")),
    taxFiling: textOf(v("tax_filing_status")),
    fxExposure: textOf(v("fx_exposure_note")),
    localContent: textOf(v("local_content_or_ownership_note")),
  };
}

export function toWire(form: FounderForm) {
  const country = COUNTRY_TO_CODE[form.location];
  const wire: Record<string, unknown> = {};
  if (form.company.trim()) wire.name = form.company.trim();
  if (form.sector.trim()) wire.sector = form.sector.trim();
  if (form.stage && STAGE_TO_WIRE[form.stage]) wire.stage = STAGE_TO_WIRE[form.stage];
  if (country) {
    wire.country = country.code;
    wire.currency = country.currency;
  }
  const fields: Record<string, { value: string | number | boolean; source: "founder" }> = {};
  const text: [string, string][] = [
    ["description", form.description],
    ["business_model", form.businessModel],
    ["website", form.website],
    ["market_size_note", form.marketSize],
    ["competition_note", form.competition],
    ["growth_constraint", form.growthConstraint],
    ["use_of_funds", form.useOfFunds],
    ["delivery_cost_trend", form.deliveryCostTrend],
    ["founder_experience", form.founderExperience],
    ["cap_table_summary", form.capTable],
    ["key_person_dependency", form.keyPerson],
    ["hiring_gaps", form.hiringGaps],
    ["supplier_dependencies", form.supplierDependencies],
    ["channel_dependency", form.channelDependency],
    ["material_contracts_note", form.materialContracts],
    ["legal_name", form.legalName],
    ["registration_number", form.registrationNumber],
    ["registrar", form.registrar],
    ["regulatory_licences", form.licences],
    ["capital_mix_note", form.capitalMix],
    ["tax_filing_status", form.taxFiling],
    ["fx_exposure_note", form.fxExposure],
    ["local_content_or_ownership_note", form.localContent],
  ];
  for (const [k, val] of text) if (val.trim()) fields[k] = field(val.trim());
  const year = n(form.year);
  if (year != null) fields.founded_year = field(Math.round(year));
  const incorporated = n(form.incorporationYear);
  if (incorporated != null) fields.incorporation_year = field(Math.round(incorporated));
  for (const [k, val] of [
    ["founder_count", form.founders],
    ["founders_full_time", form.foundersFullTime],
    ["team_size", form.teamSize],
    ["active_customers", form.customers],
    ["monthly_active_users", form.mau],
    ["pilot_or_lou_count", form.pilots],
    ["typical_contract_months", form.typicalContractMonths],
  ] as const) {
    const parsed = n(val);
    if (parsed != null) fields[k] = field(Math.round(parsed));
  }
  const churn = n(form.churn);
  if (churn != null) fields.monthly_churn_percent = field(churn);
  const share = n(form.largestCustomerShare);
  if (share != null) fields.largest_customer_revenue_share_percent = field(share);
  const recurring = n(form.recurringRevenue);
  if (recurring != null) fields.recurring_revenue_percent = field(recurring);
  const yesNo: [string, string][] = [
    ["ip_owned", form.ipOwned],
    ["contracts_transferable", form.contractsTransferable],
    ["operations_documented", form.operationsDocumented],
    ["systems_in_company_name", form.systemsInCompanyName],
    ["trading_before_incorporation", form.tradedBeforeIncorporation],
  ];
  for (const [k, val] of yesNo) {
    if (val) fields[k] = field(val === "Yes");
  }
  if (country) {
    const money = (key: string, raw: string) => {
      const parsed = n(raw);
      if (parsed != null) fields[key] = field(Math.round(parsed * 100));
    };
    money("monthly_revenue_minor", form.revenue);
    money("monthly_costs_minor", form.costs);
    money("cost_of_revenue_minor", form.costOfRevenue);
    money("cash_on_hand_minor", form.cash);
    money("last_12m_revenue_minor", form.revenue12m);
    money("monthly_revenue_3m_ago_minor", form.revenue3mAgo);
    money("monthly_costs_3m_ago_minor", form.costs3mAgo);
    money("monthly_marketing_spend_minor", form.marketingSpend);
    money("total_raised_minor", form.totalRaised);
    money("current_raise_target_minor", form.raiseTarget);
    money("founder_salary_minor", form.founderSalary);
    money("average_revenue_per_customer_minor", form.arpu);
    money("customer_acquisition_cost_minor", form.cac);
  }
  if (Object.keys(fields).length) wire.fields = fields;
  return wire;
}

export function firstIncompleteStep(form: FounderForm): number {
  for (let i = 0; i < ONBOARDING_STEPS.length; i++) {
    const keys = STEP_REQUIRED[i] ?? [];
    if (keys.some((k) => !String(form[k] ?? "").trim())) return i;
  }
  return ONBOARDING_STEPS.length - 1;
}

export function auditReadyCount(form: FounderForm): number {
  let count = 0;
  if (form.company.trim()) count += 1;
  if (form.sector.trim()) count += 1;
  if (form.stage.trim()) count += 1;
  if (form.location.trim()) count += 2;
  if (form.description.trim()) count += 1;
  if (form.businessModel.trim()) count += 1;
  if (form.teamSize.trim()) count += 1;
  if (form.revenue.trim()) count += 1;
  if (form.costs.trim()) count += 1;
  if (form.cash.trim()) count += 1;
  return count;
}

export function isAuditReady(form: FounderForm): boolean {
  return auditReadyCount(form) >= AUDIT_READY_TOTAL;
}
