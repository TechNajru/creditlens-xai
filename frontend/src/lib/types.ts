export interface Contribution {
  feature: string;
  label: string;
  value_display: string;
  contribution: number;
  direction: "increases_risk_score" | "decreases_risk_score";
}
export interface ExplanationAvailable {
  status: "available";
  method: string;
  version: string;
  shap_version: string;
  scale: string;
  baseline: number;
  model_output: number;
  top_risk_increasing: Contribution[];
  top_risk_reducing: Contribution[];
  reason_codes: string[];
  notes: string[];
  detail: string;
  contributions?: Contribution[];
  global_importance?: { values: { feature: string; mean_abs_shap: number }[]; computed_on: string } | null;
}
export interface ExplanationUnavailable {
  status: "unavailable";
  reason: string;
}
export type Explanation = ExplanationAvailable | ExplanationUnavailable;

export interface PredictionResponse {
  model_track?: string;
  default_probability_simulated?: number;
  default_probability_next_month?: number;
  uncalibrated_model_score: number;
  calibration_method: string;
  calibration_evaluated: boolean;
  model_version: string;
  feature_schema_version: string;
  data_provenance: string;
  derived_values: Record<string, number | boolean | null>;
  explanation: Explanation;
  limitations: string[];
}

export interface UploadIssue { row: number; field: string; problem: string; severity: "error" | "warning" }
export interface CategoryIssue { row?: number; key?: string; problem: string; severity: "error" | "warning" }
export interface PreviewTx {
  key: string; row: number; date: string; description: string; amount: number;
  direction: "credit" | "debit"; category: string;
  category_source: "supplied" | "user_correction" | "rule" | "default";
  confidence: "high" | "medium" | "low";
}
export interface UploadStats {
  rows_total: number; rows_valid: number; rows_with_errors: number;
  duplicates_excluded: number; issues_total: number; errors_total: number;
}
export interface PreviewResponse {
  stats: UploadStats; detected_mapping: Record<string, string>; date_format: string | null;
  issues: UploadIssue[]; category_issues: CategoryIssue[]; transactions: PreviewTx[];
  truncated: boolean; note: string;
}
export interface MonthRow {
  month: string; has_data: boolean; role: string;
  income_confirmed: number | null; income_likely: number | null; inflow_unverified: number | null;
  refunds: number | null; outflow_essential: number | null; outflow_debt: number | null;
  outflow_discretionary: number | null; outflow_other: number | null;
  transfer_in: number | null; transfer_out: number | null; net_cashflow: number | null;
}
export interface CashflowMetrics {
  months_used: number;
  avg_monthly_income_confirmed_or_likely: number | null;
  avg_monthly_income_confirmed_only: number | null;
  avg_monthly_unverified_inflow: number | null;
  avg_monthly_outflow: number | null;
  avg_monthly_net_cashflow: number | null;
  negative_net_cashflow_months: number;
  income_variability_cv: number | null;
  avg_monthly_essential_spend: number | null;
  observed_monthly_debt_payments: number | null;
  observed_debt_payments_note: string;
  observed_debt_to_income: number | null;
}
export interface AnalyzeResponse {
  stats: UploadStats; issues: UploadIssue[]; category_issues: CategoryIssue[];
  used_for_risk_model: boolean; purpose?: string;
  coverage: {
    first_date?: string; last_date?: string; calendar_months_in_span?: number; usable_interior_months?: number;
    gap_months?: string[]; sufficient_for_analysis: boolean; reasons: string[]; note?: string;
  };
  monthly: MonthRow[]; metrics: CashflowMetrics | null;
  recurring_income_groups?: { pattern: string; bucket: string; months_seen: number; avg_monthly_amount: number }[];
  identified_recurring_income_monthly?: number | null;
  payment_timeliness?: { computed: boolean; reason?: string; on_time_rate?: number; n_obligations?: number };
  missingness?: Record<string, number | null>;
}
export interface Categories { categories: string[]; credit: string[]; debit: string[] }

export interface Candidate { model: string; calibration: string; brier: number; roc_auc: number; log_loss: number; average_precision: number }
export interface Evaluation {
  track: "simulation" | "public";
  limitations: string[];
  report: {
    model_version: string; data_provenance: string; selected: { model: string; calibration: string };
    split_sizes: Record<string, number>;
    validation_candidates: Candidate[];
    test_metrics?: Record<string, number>; test_metrics_selected?: Record<string, number>;
    test_metrics_all_models_not_used_for_selection?: Record<string, Record<string, number | string>>;
    test_threshold_tradeoffs: { threshold: number; precision: number; recall: number; f1: number }[];
    majority_baseline: { brier_constant_base_rate: number; log_loss_constant_base_rate: number; accuracy_always_negative: number };
    calibration_curve_test: { mean_predicted: number[]; fraction_positive: number[] };
    global_importance?: { values: { feature: string; mean_abs_shap: number }[]; scale: string; computed_on: string; note: string };
  };
}

/* ---------------- Stage 4 ---------------- */
export interface LoanInputs {
  monthly_income: number; loan_amount: number; tenure_months: number; annual_interest_rate: number;
  existing_emi: number; age: number; employment_years: number; num_existing_loans: number;
  credit_history_months: number | null;
}
export interface ScenarioMetrics {
  new_loan_emi: number; total_emi: number; total_emi_to_income: number; total_interest: number;
  default_probability_simulated: number;
}
export interface PolicyRule { rule: string; threshold: number; value: number; passed: boolean }
export interface PolicyResult { policy_version: string; passes: boolean; rules: PolicyRule[] }
export interface ScenarioEval {
  inputs: LoanInputs; metrics: ScenarioMetrics; policy: PolicyResult;
  feasibility_issues: string[]; meets_policy: boolean;
}
export interface ScenarioResult extends ScenarioEval {
  name?: string;
  changed_inputs: Record<string, { from: number; to: number }>;
  unchanged_inputs: string[]; hypothetical: string[];
  delta_vs_base: ScenarioMetrics; change_cost?: number;
}
export interface PolicyDescription {
  version: string; max_default_probability: number; max_total_emi_to_income: number;
  min_loan_amount: number; min_tenure_months: number; max_tenure_months: number; disclaimer: string;
}
export interface WhatIfResponse { policy: PolicyDescription; base: ScenarioEval; scenarios: ScenarioResult[]; notes: string[] }
export interface CounterfactualResponse {
  status: "found" | "already_meets_policy" | "no_feasible_alternative";
  message: string; policy: PolicyDescription; base: ScenarioEval;
  alternatives: ScenarioResult[]; closest_attempt: ScenarioResult | null; notes: string[];
  search: { mutable_inputs: string[]; never_changed: string[]; ranking: string; candidates_evaluated?: number;
            searched_range?: { loan_amount: number[]; tenure_months: number[] } };
}

export interface RateWithCI { value: number | null; ci95: number[] | null; n: number; reliable?: boolean }
export interface FairnessGroup {
  group: string; n: number; defaulters: number; non_defaulters: number; reliable: boolean;
  flagged_rate: RateWithCI; favourable_rate: RateWithCI; observed_default_rate: RateWithCI;
  false_positive_rate: RateWithCI; false_negative_rate: RateWithCI;
  mean_predicted_probability: number; calibration_gap: number; calibration_gap_reliable: boolean;
  warnings: string[];
}
export interface DisparitySummary {
  computed: boolean; reason?: string; groups_included?: string[]; groups_excluded_small: string[];
  demographic_parity_difference?: number; demographic_parity_ratio?: number; equalized_odds_difference?: number;
  false_positive_rate_difference?: number; false_negative_rate_difference?: number;
}
export interface FairnessReport {
  model_version: string; data_provenance: string; evaluated_on: string; n_test: number;
  threshold: { value: number; chosen_on: string; criterion: string; experimental: boolean };
  definitions: Record<string, string>; label_note: string;
  limits: { min_group_n: number; min_class_n: number; intervals: string };
  attributes: Record<string, { groups: FairnessGroup[]; summary: DisparitySummary; warnings: string[] }>;
  mitigation: {
    attribute: string; method: string; fit_on: string; evaluated_on: string; deployed: boolean;
    implications: string[];
    tradeoffs: { metric: string; baseline: number | null; mitigated: number | null }[];
    mitigated: { calibration: string };
  };
  caveats: string[];
}

export interface ExperimentVariant {
  months_visible: number; label: string; n_features: number; roc_auc: number; roc_auc_ci95: number[];
  brier: number; log_loss: number; ece: number; roc_auc_change_vs_full: number;
}
export interface ExperimentsReport {
  label: string; data_provenance: string; evaluated_on: string; n_test: number; recipe: string;
  baseline_constant_brier: number; variants: ExperimentVariant[]; caveats: string[];
}
