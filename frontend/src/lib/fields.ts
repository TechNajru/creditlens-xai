export interface FieldSpec {
  name: string; label: string; hint?: string; min: number; max: number; integer?: boolean; optional?: boolean;
  group?: string;
}
export interface AssessmentConfig {
  key: "loan" | "public";
  title: string;
  endpoint: string;
  fields: FieldSpec[];
  examples: { label: string; values: Record<string, string> }[];
  introNote: string;
}

export const LOAN_FIELDS: FieldSpec[] = [
  { name: "monthly_income", label: "Monthly income", hint: "Before the new loan. Must be above 0.", min: 1, max: 10_000_000 },
  { name: "loan_amount", label: "Requested loan amount", min: 1, max: 100_000_000 },
  { name: "tenure_months", label: "Loan tenure (months)", hint: "3 to 360", min: 3, max: 360, integer: true },
  { name: "annual_interest_rate", label: "Interest rate (% per year)", hint: "0 means interest-free.", min: 0, max: 60 },
  { name: "existing_emi", label: "Existing monthly EMI", hint: "Total of loan instalments you already pay. Use 0 if none.", min: 0, max: 10_000_000 },
  { name: "age", label: "Age (years)", min: 18, max: 100, integer: true },
  { name: "employment_years", label: "Years in current employment", min: 0, max: 60 },
  { name: "num_existing_loans", label: "Number of existing loans", min: 0, max: 50, integer: true },
  { name: "credit_history_months", label: "Credit history length (months)", hint: "Tick “unknown” if you do not have this. Unknown is not treated as zero.", min: 0, max: 1200, optional: true },
];

const MONTHS = ["Sep 2005", "Aug 2005", "Jul 2005", "Jun 2005", "May 2005", "Apr 2005"];
const PAYS = ["PAY_0", "PAY_2", "PAY_3", "PAY_4", "PAY_5", "PAY_6"];
export const PUBLIC_FIELDS: FieldSpec[] = [
  { name: "LIMIT_BAL", label: "Credit limit (NT$)", min: 1, max: 10_000_000, group: "Account" },
  { name: "AGE", label: "Age (years)", min: 18, max: 100, integer: true, group: "Account" },
  ...PAYS.map((n, i): FieldSpec => ({
    name: n, label: `Repayment status, ${MONTHS[i]}`, integer: true, min: -2, max: 9, group: "Repayment status",
    hint: i === 0 ? "-1 = paid duly; 1–9 = months delayed. -2 and 0 occur in the data but are not defined by the dataset source." : undefined,
  })),
  ...MONTHS.map((m, i): FieldSpec => ({ name: `BILL_AMT${i + 1}`, label: `Bill statement, ${m} (NT$)`, min: -10_000_000, max: 10_000_000, group: "Bill amounts", hint: i === 0 ? "Can be negative (credit balance)." : undefined })),
  ...MONTHS.map((m, i): FieldSpec => ({ name: `PAY_AMT${i + 1}`, label: `Payment made, ${m} (NT$)`, min: 0, max: 10_000_000, group: "Payments" })),
];

const payset = (v: number[]) => Object.fromEntries(PAYS.map((n, i) => [n, String(v[i])]));
const series = (prefix: string, v: number[]) => Object.fromEntries(v.map((x, i) => [`${prefix}${i + 1}`, String(x)]));

export const LOAN_CONFIG: AssessmentConfig = {
  key: "loan",
  title: "Loan application — simulation model",
  endpoint: "/api/v1/assessments/predict?detail=full",
  fields: LOAN_FIELDS,
  introNote: "This model was trained on SYNTHETIC data. Its output demonstrates the pipeline; it says nothing about real borrowers.",
  examples: [
    { label: "Example: moderate burden", values: { monthly_income: "50000", loan_amount: "300000", tenure_months: "36", annual_interest_rate: "12", existing_emi: "5000", age: "32", employment_years: "5", num_existing_loans: "1", credit_history_months: "48" } },
    { label: "Example: heavy burden, no history", values: { monthly_income: "40000", loan_amount: "1200000", tenure_months: "36", annual_interest_rate: "14", existing_emi: "15000", age: "27", employment_years: "2", num_existing_loans: "2", credit_history_months: "" } },
  ],
};

export const PUBLIC_CONFIG: AssessmentConfig = {
  key: "public",
  title: "Credit-card default — public-data model (UCI)",
  endpoint: "/api/v1/assessments/predict-public?detail=full",
  fields: PUBLIC_FIELDS,
  introNote: "Trained on 2005 Taiwan credit-card clients (public UCI data, CC BY 4.0). Not validated for any other population, year or product.",
  examples: [
    { label: "Example: pays duly", values: { LIMIT_BAL: "200000", AGE: "40", ...payset([-1, -1, -1, -1, -1, -1]), ...series("BILL_AMT", [3000, 2500, 2800, 3000, 2000, 2200]), ...series("PAY_AMT", [3000, 2500, 2800, 3000, 2000, 2200]) } },
    { label: "Example: repeated delays", values: { LIMIT_BAL: "50000", AGE: "29", ...payset([3, 3, 2, 2, 2, 2]), ...series("BILL_AMT", [48000, 47000, 46000, 45000, 44000, 43000]), ...series("PAY_AMT", [0, 0, 1000, 0, 0, 0]) } },
  ],
};

export function validateFields(specs: FieldSpec[], values: Record<string, string>, unknown: Record<string, boolean> = {}) {
  const errors: Record<string, string> = {};
  const payload: Record<string, number | null> = {};
  for (const f of specs) {
    if (f.optional && unknown[f.name]) { payload[f.name] = null; continue; }
    const raw = (values[f.name] ?? "").trim();
    if (raw === "") { errors[f.name] = f.optional ? "Enter a value or tick “unknown”." : "This field is required."; continue; }
    const n = Number(raw.replace(/,/g, ""));
    if (!Number.isFinite(n)) { errors[f.name] = "Enter a number."; continue; }
    if (f.integer && !Number.isInteger(n)) { errors[f.name] = "Enter a whole number."; continue; }
    if (n < f.min || n > f.max) { errors[f.name] = `Must be between ${f.min.toLocaleString("en-US")} and ${f.max.toLocaleString("en-US")}.`; continue; }
    payload[f.name] = n;
  }
  return { errors, payload, ok: Object.keys(errors).length === 0 };
}
