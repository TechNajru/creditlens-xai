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

/* ---------------- Stage 5: accounts, applications, review, admin ---------------- */
export type Role = "applicant" | "reviewer" | "admin";
export interface User { id: number; email: string; role: Role }
export interface MeResponse { user: User; csrf_token: string }
export type AppStatus = "draft" | "submitted" | "validation" | "assessed" | "manual_review" | "info_requested" | "final_demo_decision";

export interface AppSummary {
  id: string; status: AppStatus; created_at: string; updated_at: string; submitted_at: string | null;
  loan_amount: number | null; tenure_months: number | null; probability: number | null; decision: string | null;
}
export interface InfoRequestView { id: number; message: string; created_at: string; response: string | null; responded_at: string | null }
export interface UploadInfo {
  filename: string; size_bytes: number; rows_total: number; rows_valid: number; rows_with_errors: number;
  duplicates_excluded: number; date_format: string | null; issues: UploadIssue[]; uploaded_at: string;
}
export interface AssessmentView {
  id: number; is_preview: boolean; created_at: string; model_version: string; feature_schema_version: string;
  policy_version: string; policy_result: PolicyResult; result: PredictionResponse;
}
export interface FinalDecision { id: number; decision: string; reason: string; created_at: string;
  policy_recommendation?: string; is_override?: boolean; override_reason?: string | null }
export interface TimelineEvent { ts: string; action: string; details: Record<string, unknown> }
export interface ApplicantApplication extends AppSummary {
  loan_inputs: Record<string, number | null>; upload: UploadInfo | null; editable: boolean;
  assessment: AssessmentView | null; info_requests: InfoRequestView[]; final_decision: FinalDecision | null;
  timeline: TimelineEvent[];
}
export interface StoredTx {
  id: number; key: string; row: number; date: string; description: string; amount: number;
  direction: "credit" | "debit"; category: string; category_source: string; confidence: "high" | "medium" | "low";
}
export interface TransactionsResponse { transactions: StoredTx[]; credit_categories: string[]; debit_categories: string[] }
export interface UploadResponse { upload: UploadInfo; category_issues: CategoryIssue[]; transactions: StoredTx[]; truncated: boolean }

export interface ReviewQueueRow extends AppSummary { applicant_ref: string; review_reason_codes: string[]; policy_passes: boolean | null }
export interface ReviewDetailData extends AppSummary {
  applicant_ref: string; loan_inputs: Record<string, number | null>;
  review_reasons: { code: string; message: string }[];
  input_quality: { credit_history: string; cashflow_provided: boolean; cashflow_sufficient: boolean | null;
    upload_rows_with_errors: number | null; upload_duplicates_excluded: number | null; low_confidence_value_share: number | null };
  upload: UploadInfo | null; transactions: StoredTx[]; cashflow: AnalyzeResponse | null;
  assessment: AssessmentView | null; preview_assessments: number; policy_recommendation: string | null;
  info_requests: InfoRequestView[]; decisions: FinalDecision[];
  timeline: { id: number; ts: string; actor_role: string; action: string; details: Record<string, unknown> }[];
}

export interface AdminUser { id: number; email: string; role: Role; is_active: boolean; created_at: string; applications: number }
export interface AdminModel {
  id: number; track: "simulation" | "public"; version: string; artifact_sha256: string; is_active: boolean;
  registered_at: string; activated_at: string | null; summary: Record<string, unknown>;
}
export interface MonitoringData {
  applications_by_status: Record<string, number>;
  assessments: { official: number; preview: number; official_by_model_version: Record<string, number> };
  prediction_distribution: { n: number; mean: number; p10: number; p50: number; p90: number; histogram_10_bins: number[] } | null;
  input_missingness: { submitted_applications: number; credit_history_unknown_share: number | null; no_cashflow_file_share: number | null };
  review: { decisions: number; approved_share: number | null; override_share: number | null };
  notes: string[];
}
export interface AuditEventView { id: number; ts: string; actor_role: string; actor_id: number | null; action: string;
  entity_type: string; entity_id: string; application_id: string | null; details: Record<string, unknown> }
