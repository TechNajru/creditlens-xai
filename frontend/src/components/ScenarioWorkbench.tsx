"use client";
import { useState } from "react";
import { ApiError, postJson } from "@/lib/api";
import { LOAN_CONFIG, LOAN_FIELDS, validateFields } from "@/lib/fields";
import type { CounterfactualResponse, ScenarioResult, WhatIfResponse } from "@/lib/types";
import { money, pct, titleCase } from "@/lib/format";
import { NumberField } from "./NumberField";
import { Notice, Spinner } from "./Notice";
import { ScenarioTable } from "./ScenarioTable";

const EDITABLE = [
  { name: "loan_amount", label: "Loan amount" },
  { name: "tenure_months", label: "Tenure (months)" },
  { name: "annual_interest_rate", label: "Interest rate (%)" },
  { name: "existing_emi", label: "Existing monthly EMI (hypothetical debt reduction)" },
] as const;
type Draft = { name: string; changes: Record<string, string> };
const BLANK = (i: number): Draft => ({ name: `Scenario ${String.fromCharCode(65 + i)}`, changes: {} });

function AlternativeCard({ alt, index, closest = false }: { alt: ScenarioResult; index: number; closest?: boolean }) {
  const interestDelta = alt.delta_vs_base.total_interest;
  return (
    <li className="rounded-lg border border-slate-200 p-4 dark:border-slate-700">
      <h4 className="font-semibold">{closest ? "Closest attempt (does not pass)" : `Alternative ${index + 1}`}</h4>
      <p className="mt-1 text-sm"><span className="font-medium">Changed:</span>{" "}
        {Object.entries(alt.changed_inputs).map(([k, v]) => `${titleCase(k)} ${v.from.toLocaleString("en-IN")} → ${v.to.toLocaleString("en-IN")}`).join("; ") || "nothing"}
      </p>
      {alt.hypothetical.length > 0 && (
        <p className="mt-1 text-sm font-medium text-amber-800 dark:text-amber-200">Hypothetical: this assumes you actually reduce existing debt payments. It is not something the application can simply claim.</p>
      )}
      <p className="mt-1 text-sm"><span className="font-medium">Unchanged:</span> {alt.unchanged_inputs.map(titleCase).join(", ")}</p>
      <dl className="mt-2 grid gap-x-6 gap-y-1 text-sm md:grid-cols-2">
        <dt className="text-slate-500">Simulated default probability</dt><dd className="tabular-nums">{pct(alt.metrics.default_probability_simulated)} ({alt.delta_vs_base.default_probability_simulated >= 0 ? "+" : "−"}{Math.abs(alt.delta_vs_base.default_probability_simulated * 100).toFixed(1)} pts model output)</dd>
        <dt className="text-slate-500">EMI of this loan</dt><dd className="tabular-nums">{money(alt.metrics.new_loan_emi)}</dd>
        <dt className="text-slate-500">Total EMI ÷ income</dt><dd className="tabular-nums">{pct(alt.metrics.total_emi_to_income, 0)}</dd>
        <dt className="text-slate-500">Total interest over the term</dt>
        <dd className="tabular-nums">{money(alt.metrics.total_interest)} ({interestDelta >= 0 ? "+" : "−"}{money(Math.abs(interestDelta))} vs requested)</dd>
      </dl>
      <ul className="mt-2 text-xs text-slate-600 dark:text-slate-400">
        {alt.policy.rules.map((r) => <li key={r.rule}>{r.passed ? "✓" : "✗"} {r.rule}</li>)}
        {alt.feasibility_issues.map((f) => <li key={f}>✗ {f}</li>)}
      </ul>
    </li>
  );
}

export function ScenarioWorkbench() {
  const [values, setValues] = useState<Record<string, string>>({});
  const [unknown, setUnknown] = useState<Record<string, boolean>>({});
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [drafts, setDrafts] = useState<Draft[]>([BLANK(0)]);
  const [maxProb, setMaxProb] = useState("20");
  const [maxEmi, setMaxEmi] = useState("50");
  const [allowDebt, setAllowDebt] = useState(false);
  const [busy, setBusy] = useState<null | "whatif" | "cf">(null);
  const [error, setError] = useState<string | null>(null);
  const [whatIf, setWhatIf] = useState<WhatIfResponse | null>(null);
  const [cf, setCf] = useState<CounterfactualResponse | null>(null);

  function base() {
    const v = validateFields(LOAN_FIELDS, values, unknown);
    setErrors(v.errors);
    const p = Number(maxProb), e = Number(maxEmi);
    if (!(p > 0 && p <= 100) || !(e > 0 && e <= 500)) { setError("Policy limits must be between 0 and 100% (probability) and 0 and 500% (EMI ratio)."); return null; }
    return v.ok ? { application: v.payload, policy: { max_default_probability: p / 100, max_total_emi_to_income: e / 100 } } : null;
  }

  async function run(kind: "whatif" | "cf") {
    setError(null);
    const b = base();
    if (!b) return;
    let body: unknown;
    if (kind === "whatif") {
      const scenarios = drafts.map((d) => ({
        name: d.name.trim() || "Scenario",
        changes: Object.fromEntries(Object.entries(d.changes).filter(([, v]) => v.trim() !== "").map(([k, v]) => [k, Number(v.replace(/,/g, ""))])),
      }));
      if (scenarios.some((s) => Object.keys(s.changes).length === 0)) { setError("Each scenario needs at least one changed value."); return; }
      if (scenarios.some((s) => Object.values(s.changes).some((n) => !Number.isFinite(n)))) { setError("Scenario values must be numbers."); return; }
      body = { ...b, scenarios };
    } else {
      body = { ...b, allow_hypothetical_debt_reduction: allowDebt, max_results: 3 };
    }
    setBusy(kind);
    try {
      if (kind === "whatif") setWhatIf(await postJson<WhatIfResponse>("/api/v1/scenarios/what-if", body));
      else setCf(await postJson<CounterfactualResponse>("/api/v1/scenarios/counterfactuals", body));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Something went wrong. Please try again.");
    } finally { setBusy(null); }
  }

  function fill(example: Record<string, string>) {
    setValues(example);
    setUnknown({ credit_history_months: (example.credit_history_months ?? "") === "" });
    setErrors({}); setError(null); setWhatIf(null); setCf(null);
  }

  return (
    <div className="space-y-8">
      <Notice tone="info" title="Simulation only">
        Uses the synthetic-data loan model. Only loan amount, tenure and interest rate can be varied. Income, age, employment
        history, number of loans and credit history are facts about you and can never be changed here. Reducing existing EMI is shown
        only as an explicitly hypothetical scenario.
      </Notice>

      <section aria-labelledby="base-h" className="space-y-3">
        <h2 id="base-h" className="text-xl font-semibold">1. Base application</h2>
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-sm text-slate-600 dark:text-slate-300">Fictional examples:</span>
          {LOAN_CONFIG.examples.map((ex) => (
            <button key={ex.label} type="button" onClick={() => fill(ex.values)}
              className="rounded-md border border-slate-300 px-3 py-1 text-sm hover:bg-slate-100 dark:border-slate-600 dark:hover:bg-slate-800">{ex.label}</button>
          ))}
        </div>
        <div className="grid gap-4 md:grid-cols-2">
          {LOAN_FIELDS.map((f) => (
            <div key={f.name}>
              <NumberField id={`base-${f.name}`} label={f.label} hint={f.hint} value={values[f.name] ?? ""} error={errors[f.name]}
                disabled={f.optional && unknown[f.name]} onChange={(v) => setValues((s) => ({ ...s, [f.name]: v }))} />
              {f.optional && (
                <label className="mt-1 flex items-center gap-2 text-sm">
                  <input type="checkbox" checked={!!unknown[f.name]} onChange={(e) => setUnknown((s) => ({ ...s, [f.name]: e.target.checked }))} />
                  Unknown / not available
                </label>
              )}
            </div>
          ))}
        </div>
        <fieldset className="rounded-lg border border-slate-200 p-3 dark:border-slate-700">
          <legend className="px-1 text-sm font-semibold">Demonstration policy (experimental thresholds)</legend>
          <div className="grid gap-4 md:grid-cols-2">
            <NumberField id="policy-prob" label="Max simulated default probability (%)" value={maxProb} onChange={setMaxProb} />
            <NumberField id="policy-emi" label="Max total EMI ÷ income (%)" value={maxEmi} onChange={setMaxEmi} />
          </div>
        </fieldset>
      </section>

      {error && <Notice tone="error" title="Could not run">{error}</Notice>}
      {Object.keys(errors).length > 0 && <Notice tone="error" title="Please fix the highlighted fields">{Object.keys(errors).length} field(s) need attention.</Notice>}

      <section aria-labelledby="wi-h" className="space-y-4">
        <h2 id="wi-h" className="text-xl font-semibold">2. What-if simulator</h2>
        <p className="text-sm text-slate-600 dark:text-slate-300">Leave a field blank to keep the base value. Up to 3 scenarios.</p>
        <div className="grid gap-4 md:grid-cols-3">
          {drafts.map((d, i) => (
            <section key={i} aria-label={`Scenario ${i + 1}`} className="space-y-2 rounded-lg border border-slate-200 p-3 dark:border-slate-700">
              <NumberField id={`sc-${i}-name`} label="Name" value={d.name} onChange={(v) => setDrafts((s) => s.map((x, j) => (j === i ? { ...x, name: v } : x)))} />
              {EDITABLE.map((f) => (
                <NumberField key={f.name} id={`sc-${i}-${f.name}`} label={f.label} value={d.changes[f.name] ?? ""}
                  hint={values[f.name] ? `Base: ${values[f.name]}` : undefined}
                  onChange={(v) => setDrafts((s) => s.map((x, j) => (j === i ? { ...x, changes: { ...x.changes, [f.name]: v } } : x)))} />
              ))}
              {drafts.length > 1 && (
                <button type="button" onClick={() => setDrafts((s) => s.filter((_, j) => j !== i))} className="text-sm underline">Remove scenario</button>
              )}
            </section>
          ))}
        </div>
        <div className="flex flex-wrap gap-3">
          {drafts.length < 3 && (
            <button type="button" onClick={() => setDrafts((s) => [...s, BLANK(s.length)])} className="rounded-md border border-slate-400 px-3 py-1 text-sm">Add scenario</button>
          )}
          <button type="button" disabled={busy !== null} onClick={() => run("whatif")}
            className="rounded-md bg-sky-700 px-4 py-2 text-sm font-medium text-white hover:bg-sky-800 disabled:opacity-50">
            {busy === "whatif" ? "Comparing…" : "Compare scenarios"}
          </button>
        </div>
        {busy === "whatif" && <Spinner label="Re-scoring each scenario…" />}
        {whatIf && (
          <div className="space-y-3">
            <ScenarioTable columns={[{ title: "Base", ev: whatIf.base, isBase: true }, ...whatIf.scenarios.map((s) => ({ title: s.name ?? "Scenario", ev: s }))]} />
            <Notice tone="warning" title="Read carefully"><ul className="list-disc pl-5">{whatIf.notes.map((n) => <li key={n}>{n}</li>)}</ul></Notice>
          </div>
        )}
        {!whatIf && busy !== "whatif" && <p className="text-sm text-slate-600 dark:text-slate-400">No comparison yet.</p>}
      </section>

      <section aria-labelledby="cf-h" className="space-y-4">
        <h2 id="cf-h" className="text-xl font-semibold">3. Find alternatives that meet the demonstration policy</h2>
        <label className="flex items-start gap-2 text-sm">
          <input type="checkbox" className="mt-1" checked={allowDebt} onChange={(e) => setAllowDebt(e.target.checked)} />
          <span>Also consider hypothetical reductions in existing EMI (only meaningful if you could really pay that debt down)</span>
        </label>
        <button type="button" disabled={busy !== null} onClick={() => run("cf")}
          className="rounded-md bg-sky-700 px-4 py-2 text-sm font-medium text-white hover:bg-sky-800 disabled:opacity-50">
          {busy === "cf" ? "Searching…" : "Find alternatives"}
        </button>
        {busy === "cf" && <Spinner label="Searching allowed combinations…" />}
        {cf && (
          <div className="space-y-3" aria-live="polite">
            <Notice tone={cf.status === "found" ? "success" : cf.status === "already_meets_policy" ? "info" : "warning"}
              title={cf.status === "found" ? "Alternatives found" : cf.status === "already_meets_policy" ? "No change needed" : "No feasible alternative"}>
              {cf.message}
            </Notice>
            <p className="text-xs text-slate-500">
              Searched: loan amount {cf.search.searched_range ? `${money(cf.search.searched_range.loan_amount[0])}–${money(cf.search.searched_range.loan_amount[1])}` : ""}, tenure {cf.search.searched_range ? `${cf.search.searched_range.tenure_months[0]}–${cf.search.searched_range.tenure_months[1]} months` : ""}
              {cf.search.candidates_evaluated ? ` (${cf.search.candidates_evaluated} combinations)` : ""}. Never changed: {cf.search.never_changed.map(titleCase).join(", ")}.
            </p>
            {cf.alternatives.length > 0 && (
              <>
                <ul className="space-y-3">{cf.alternatives.map((a, i) => <AlternativeCard key={i} alt={a} index={i} />)}</ul>
                <ScenarioTable columns={[{ title: "Requested", ev: cf.base, isBase: true }, ...cf.alternatives.map((a, i) => ({ title: `Alternative ${i + 1}`, ev: a }))]} />
              </>
            )}
            {cf.status === "no_feasible_alternative" && cf.closest_attempt && <ul><AlternativeCard alt={cf.closest_attempt} index={0} closest /></ul>}
            <Notice tone="warning" title="Read carefully"><ul className="list-disc pl-5">{cf.notes.map((n) => <li key={n}>{n}</li>)}</ul></Notice>
          </div>
        )}
      </section>
    </div>
  );
}
