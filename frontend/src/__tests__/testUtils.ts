import { vi } from "vitest";

type Handler = () => { status?: number; body?: unknown } | Promise<{ status?: number; body?: unknown }>;

/** Replace global fetch with route handlers keyed by a URL substring. */
export function mockFetch(routes: Record<string, Handler>) {
  const fn = vi.fn(async (url: string | URL | Request) => {
    const u = String(url);
    const key = Object.keys(routes).find((k) => u.includes(k));
    if (!key) throw new Error(`unmocked fetch: ${u}`);
    const { status = 200, body = {} } = await routes[key]();
    return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
  });
  vi.stubGlobal("fetch", fn);
  return fn;
}

export const PREDICTION = {
  model_track: "simulation",
  default_probability_simulated: 0.123,
  uncalibrated_model_score: 0.1,
  calibration_method: "sigmoid",
  calibration_evaluated: true,
  model_version: "sim-test-v1",
  feature_schema_version: "1.0.0",
  data_provenance: "SYNTHETIC simulation data (fictional; not real borrowers)",
  derived_values: { new_loan_emi: 9964.3, total_emi_to_income: 0.3, credit_history_missing: true },
  explanation: {
    status: "available", method: "SHAP PermutationExplainer", version: "shap-permutation-v1", shap_version: "0.54.1",
    scale: "uncalibrated model risk score", baseline: 0.18, model_output: 0.1,
    top_risk_increasing: [{ feature: "total_emi_to_income", label: "Total EMI as a share of monthly income", value_display: "30%", contribution: 0.05, direction: "increases_risk_score" }],
    top_risk_reducing: [],
    reason_codes: ["Total EMI as a share of monthly income: 30% — raised the model's risk score"],
    notes: ["Contributions add up to the model's raw risk score."], detail: "full",
  },
  limitations: ["Trained on synthetic data: performance says nothing about real borrowers."],
};
