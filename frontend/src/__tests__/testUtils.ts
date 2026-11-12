import { vi } from "vitest";

type Req = { url: string; method: string; body: unknown; headers: Headers; credentials?: RequestCredentials };
type Handler = (req: Req) => { status?: number; body?: unknown } | Promise<{ status?: number; body?: unknown }>;

/**
 * Replace global fetch with route handlers.
 * A key is either a URL substring ("/auth/me") or "METHOD substring" ("POST /submit"). First match wins,
 * so list more specific routes before more general ones.
 */
export function mockFetch(routes: Record<string, Handler | (() => { status?: number; body?: unknown })>) {
  const fn = vi.fn(async (url: string | URL | Request, init?: RequestInit) => {
    const u = String(url);
    const method = (init?.method ?? "GET").toUpperCase();
    const key = Object.keys(routes).find((k) => {
      const m = k.match(/^(GET|POST|PATCH|DELETE) (.*)$/);
      return m ? m[1] === method && u.includes(m[2]) : u.includes(k);
    });
    if (!key) throw new Error(`unmocked fetch: ${method} ${u}`);
    let body: unknown = init?.body;
    if (typeof body === "string") { try { body = JSON.parse(body); } catch { /* leave as string */ } }
    const { status = 200, body: resBody = {} } = await (routes[key] as Handler)({ url: u, method, body, headers: new Headers(init?.headers), credentials: init?.credentials });
    return new Response(JSON.stringify(resBody), { status, headers: { "Content-Type": "application/json" } });
  });
  vi.stubGlobal("fetch", fn);
  return fn;
}

export const lastCall = (fn: ReturnType<typeof mockFetch>, method: string, part: string) => {
  const calls = fn.mock.calls as unknown as [string, RequestInit | undefined][];
  const hit = [...calls].reverse().find(([u, i]) => String(u).includes(part) && (i?.method ?? "GET").toUpperCase() === method);
  if (!hit) throw new Error(`no ${method} call containing ${part}`);
  return { url: String(hit[0]), init: hit[1] ?? {}, body: typeof hit[1]?.body === "string" ? JSON.parse(hit[1].body as string) : hit[1]?.body };
};

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
