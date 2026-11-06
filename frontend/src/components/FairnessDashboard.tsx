"use client";
import { useEffect, useState } from "react";
import { ApiError, getJson } from "@/lib/api";
import type { FairnessGroup, FairnessReport, RateWithCI } from "@/lib/types";
import { pct } from "@/lib/format";
import { Notice, Spinner } from "./Notice";

const ATTR_LABEL: Record<string, string> = { SEX: "Sex", EDUCATION: "Education", MARRIAGE: "Marital status", AGE_GROUP: "Age group" };

function rate(r: RateWithCI, ok = true) {
  if (r.value === null) return "—";
  const ci = r.ci95 ? ` (${pct(r.ci95[0], 1)}–${pct(r.ci95[1], 1)})` : "";
  return `${pct(r.value, 1)}${ci}${ok ? "" : " ⚠"}`;
}

function Row({ g }: { g: FairnessGroup }) {
  return (
    <tr className={`border-b border-slate-100 align-top dark:border-slate-800 ${g.reliable ? "" : "text-slate-500"}`}>
      <th scope="row" className="py-1 pr-3 text-left font-medium">{g.group}</th>
      <td className="pr-3 tabular-nums">{g.n.toLocaleString("en-IN")}</td>
      <td className="pr-3 tabular-nums">
        {rate(g.flagged_rate)}
        {g.flagged_rate.value !== null && <div aria-hidden="true" className="mt-1 h-1.5 rounded bg-sky-600" style={{ width: `${Math.min(100, g.flagged_rate.value * 100)}%` }} />}
      </td>
      <td className="pr-3 tabular-nums">{rate(g.false_positive_rate, g.false_positive_rate.reliable)}</td>
      <td className="pr-3 tabular-nums">{rate(g.false_negative_rate, g.false_negative_rate.reliable)}</td>
      <td className="pr-3 tabular-nums">{rate(g.observed_default_rate)}</td>
      <td className="pr-3 tabular-nums">{g.calibration_gap >= 0 ? "+" : "−"}{Math.abs(g.calibration_gap).toFixed(3)}{g.calibration_gap_reliable ? "" : " ⚠"}</td>
      <td className="text-xs">{g.reliable ? (g.warnings.length ? g.warnings.join("; ") : "Reasonable sample") : <strong>Unreliable: {g.warnings.join("; ")}</strong>}</td>
    </tr>
  );
}

export function FairnessDashboard() {
  const [state, setState] = useState<{ data?: FairnessReport; error?: string } | null>(null);
  const [attr, setAttr] = useState("SEX");

  useEffect(() => {
    let cancelled = false;
    getJson<FairnessReport>("/api/v1/fairness/public")
      .then((data) => { if (!cancelled) setState({ data }); })
      .catch((e) => {
        if (cancelled) return;
        setState({ error: e instanceof ApiError && e.status === 404
          ? "No fairness report yet. Generate it with: python -m app.fairness (after python -m app.public_train)."
          : e instanceof ApiError ? e.message : "Could not load the fairness report." });
      });
    return () => { cancelled = true; };
  }, []);

  if (!state) return <Spinner label="Loading fairness report…" />;
  if (state.error) return <Notice tone="error" title="Fairness report not available">{state.error}</Notice>;
  const r = state.data!;
  const a = r.attributes[attr];
  const m = r.mitigation;
  const fmt = (metric: string, v: number | null) => (v === null ? "—" : metric.includes("difference") ? v.toFixed(3) : pct(v, 1));

  return (
    <div className="space-y-8">
      <Notice tone="warning" title="Sensitive attributes — handle with care">
        Sex, education and marital status are used here only to measure outcomes; they are <strong>not</strong> model inputs. <strong>Age is a model input</strong> and
        is also audited by age group (age-based credit decisions are restricted in some places). Dropping columns does not remove proxy bias.
        Access to this page should be restricted (access control arrives with accounts and roles).
      </Notice>
      <section aria-labelledby="def-h" className="space-y-2">
        <h2 id="def-h" className="text-lg font-semibold">What is being measured</h2>
        <ul className="list-disc space-y-1 pl-5 text-sm">
          <li><strong>Positive prediction:</strong> {r.definitions.positive_prediction}</li>
          <li><strong>Favourable outcome:</strong> {r.definitions.favourable_outcome}</li>
          <li><strong>Harm focus:</strong> {r.definitions.false_positive_rate}</li>
        </ul>
        <p className="text-sm text-slate-600 dark:text-slate-300">
          Model {r.model_version}. Threshold {r.threshold.value} (chosen on the {r.threshold.chosen_on} by {r.threshold.criterion}; experimental, not a policy).
          All numbers come from the {r.evaluated_on} ({r.n_test.toLocaleString("en-IN")} clients). Intervals are {r.limits.intervals}. ⚠ marks estimates with too few cases.
        </p>
        <p className="text-xs text-slate-500">{r.label_note}</p>
      </section>

      <section aria-labelledby="grp-h" className="space-y-3">
        <h2 id="grp-h" className="text-lg font-semibold">Outcomes by group</h2>
        <div role="tablist" aria-label="Attribute" className="flex flex-wrap gap-2">
          {Object.keys(r.attributes).map((k) => (
            <button key={k} role="tab" aria-selected={attr === k} onClick={() => setAttr(k)}
              className={`rounded-md border px-3 py-1.5 text-sm ${attr === k ? "border-sky-700 bg-sky-700 text-white" : "border-slate-300 dark:border-slate-600"}`}>{ATTR_LABEL[k] ?? k}</button>
          ))}
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <caption className="sr-only">Group outcomes for {ATTR_LABEL[attr] ?? attr}</caption>
            <thead><tr className="border-b border-slate-300 dark:border-slate-700">
              <th scope="col" className="py-1 pr-3">Group</th><th scope="col" className="pr-3">Clients</th>
              <th scope="col" className="pr-3">Flagged (95% CI)</th><th scope="col" className="pr-3">Wrongly flagged (FPR)</th>
              <th scope="col" className="pr-3">Missed defaults (FNR)</th><th scope="col" className="pr-3">Observed default rate</th>
              <th scope="col" className="pr-3">Calibration gap</th><th scope="col">Reliability</th>
            </tr></thead>
            <tbody>{a.groups.map((g) => <Row key={g.group} g={g} />)}</tbody>
          </table>
        </div>
        {a.summary.computed ? (
          <dl className="grid gap-3 md:grid-cols-4">
            {[["Demographic parity difference", a.summary.demographic_parity_difference], ["Demographic parity ratio", a.summary.demographic_parity_ratio],
              ["Equalized odds difference", a.summary.equalized_odds_difference], ["False-positive-rate gap", a.summary.false_positive_rate_difference]].map(([k, v]) => (
              <div key={k as string} className="rounded-lg border border-slate-200 p-3 dark:border-slate-700">
                <dt className="text-xs text-slate-500">{k as string}</dt><dd className="text-lg font-semibold tabular-nums">{(v as number).toFixed(3)}</dd>
              </div>
            ))}
          </dl>
        ) : <Notice tone="info" title="No disparity summary">{a.summary.reason}</Notice>}
        {a.summary.groups_excluded_small.length > 0 && (
          <p className="text-sm">Excluded from the summary because they are too small: {a.summary.groups_excluded_small.join(", ")}.</p>
        )}
        <p className="text-xs text-slate-500">Differences smaller than the intervals may be noise. No single number proves or disproves fairness.</p>
      </section>

      <section aria-labelledby="mit-h" className="space-y-3">
        <h2 id="mit-h" className="text-lg font-semibold">Mitigation experiment ({ATTR_LABEL[m.attribute] ?? m.attribute}) — {m.deployed ? "deployed" : "not deployed"}</h2>
        <p className="text-sm">{m.method}. Fit on the {m.fit_on}, evaluated on the {m.evaluated_on}.</p>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <caption className="sr-only">Baseline versus mitigated trade-offs</caption>
            <thead><tr className="border-b border-slate-300 dark:border-slate-700"><th scope="col" className="py-1 pr-3">Metric</th><th scope="col" className="pr-3">Baseline</th><th scope="col">Mitigated</th></tr></thead>
            <tbody>{m.tradeoffs.map((t) => (
              <tr key={t.metric} className="border-b border-slate-100 dark:border-slate-800">
                <th scope="row" className="py-1 pr-3 text-left font-normal">{t.metric}</th>
                <td className="pr-3 tabular-nums">{fmt(t.metric, t.baseline)}</td><td className="tabular-nums">{fmt(t.metric, t.mitigated)}</td>
              </tr>))}</tbody>
          </table>
        </div>
        <p className="text-sm">Calibration after mitigation: {m.mitigated.calibration}</p>
        <Notice tone="warning" title="Why this is not applied">
          <ul className="list-disc space-y-1 pl-5">{m.implications.map((i) => <li key={i}>{i}</li>)}</ul>
        </Notice>
      </section>

      <Notice tone="info" title="Caveats"><ul className="list-disc space-y-1 pl-5">{r.caveats.map((c) => <li key={c}>{c}</li>)}</ul></Notice>
    </div>
  );
}
