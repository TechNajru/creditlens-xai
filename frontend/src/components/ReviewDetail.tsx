"use client";
import { useEffect, useState } from "react";
import { ApiError, getJson, postJson } from "@/lib/api";
import type { ReviewDetailData } from "@/lib/types";
import { money, titleCase } from "@/lib/format";
import { Analysis } from "./CashflowWorkbench";
import { Notice, Spinner } from "./Notice";
import { PredictionResult } from "./PredictionResult";
import { StatusBadge } from "./StatusBadge";

const MIN = 10;
const label = (d: string) => d.replace("demo_", "");

export function ReviewDetail({ id }: { id: string }) {
  const [d, setD] = useState<ReviewDetailData | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [decision, setDecision] = useState<"demo_approved" | "demo_declined" | "">("");
  const [reason, setReason] = useState("");
  const [override, setOverride] = useState("");
  const [question, setQuestion] = useState("");
  const [formError, setFormError] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    getJson<ReviewDetailData>(`/api/v1/reviews/${id}`)
      .then((r) => { if (!cancelled) setD(r); })
      .catch((e) => { if (!cancelled) setLoadError(e instanceof ApiError ? e.message : "Could not load this application."); });
    return () => { cancelled = true; };
  }, [id]);

  if (loadError) return <Notice tone="error" title="Could not open this application">{loadError}</Notice>;
  if (!d) return <Spinner label="Loading the application…" />;

  const needsOverride = decision !== "" && d.policy_recommendation !== null && decision !== d.policy_recommendation;
  const actionable = d.status === "manual_review";

  async function send(kind: "decision" | "info") {
    setFormError(null); setError(null);
    if (kind === "info") {
      if (question.trim().length < MIN) { setFormError(`Write at least ${MIN} characters for the applicant.`); return; }
    } else {
      if (!decision) { setFormError("Choose a decision."); return; }
      if (reason.trim().length < MIN) { setFormError(`Explain your decision in at least ${MIN} characters.`); return; }
      if (needsOverride && override.trim().length < MIN) { setFormError(`This differs from the policy recommendation (${label(d!.policy_recommendation ?? "")}). An override reason of at least ${MIN} characters is required.`); return; }
    }
    setBusy(kind);
    try {
      const body = kind === "info" ? { message: question.trim() } : { decision, reason: reason.trim(), override_reason: needsOverride ? override.trim() : null };
      setD(await postJson<ReviewDetailData>(`/api/v1/reviews/${id}/${kind === "info" ? "request-info" : "decision"}`, body));
      setQuestion(""); setReason(""); setOverride(""); setDecision("");
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Something went wrong. Please try again.");
    } finally { setBusy(null); }
  }

  const a = d.assessment;
  return (
    <div className="space-y-8">
      <header className="flex flex-wrap items-center gap-3">
        <h2 className="text-xl font-semibold">Applicant {d.applicant_ref}</h2><StatusBadge status={d.status} />
        <span className="text-sm text-slate-600 dark:text-slate-300">Submitted {d.submitted_at?.slice(0, 10) ?? "—"}</span>
      </header>

      <section aria-labelledby="why-h" className="space-y-2">
        <h3 id="why-h" className="text-lg font-semibold">Why this is in review</h3>
        <ul className="list-disc space-y-1 pl-5 text-sm">{d.review_reasons.map((r) => <li key={r.code}>{r.message}</li>)}</ul>
        <h3 className="pt-2 text-lg font-semibold">Input quality</h3>
        <dl className="grid gap-x-6 gap-y-1 text-sm md:grid-cols-2">
          <dt className="text-slate-500">Credit history</dt><dd>{d.input_quality.credit_history}</dd>
          <dt className="text-slate-500">Transaction file</dt><dd>{d.input_quality.cashflow_provided ? (d.input_quality.cashflow_sufficient ? "provided, coverage sufficient" : "provided, coverage INSUFFICIENT") : "not provided"}</dd>
          <dt className="text-slate-500">Rows with errors / duplicates excluded</dt><dd>{d.input_quality.upload_rows_with_errors ?? "—"} / {d.input_quality.upload_duplicates_excluded ?? "—"}</dd>
          <dt className="text-slate-500">Value in low-confidence categories</dt><dd>{d.input_quality.low_confidence_value_share === null ? "—" : `${(d.input_quality.low_confidence_value_share * 100).toFixed(0)}%`}</dd>
        </dl>
      </section>

      <section aria-labelledby="inp-h" className="space-y-2">
        <h3 id="inp-h" className="text-lg font-semibold">Application inputs</h3>
        <dl className="grid gap-x-6 gap-y-1 text-sm md:grid-cols-2">
          {Object.entries(d.loan_inputs).map(([k, v]) => (<div key={k} className="contents"><dt className="text-slate-500">{titleCase(k)}</dt><dd className="tabular-nums">{v === null ? "unknown" : v}</dd></div>))}
        </dl>
      </section>

      <section aria-label="Cash flow" className="space-y-2">
        {d.cashflow ? <Analysis a={d.cashflow} /> : (<><h3 className="text-lg font-semibold">Cash flow</h3><p className="text-sm text-slate-600 dark:text-slate-400">No transaction file was provided.</p></>)}
        {d.transactions.length > 0 && (
          <details className="rounded-lg border border-slate-200 p-3 dark:border-slate-700">
            <summary className="cursor-pointer text-sm font-semibold">Transactions ({d.transactions.length}, least certain first)</summary>
            <div className="mt-2 overflow-x-auto">
              <table className="w-full text-left text-sm">
                <caption className="sr-only">Applicant transactions</caption>
                <thead><tr className="border-b border-slate-300 dark:border-slate-700"><th scope="col" className="py-1 pr-3">Date</th><th scope="col" className="pr-3">Description</th><th scope="col" className="pr-3 text-right">Amount</th><th scope="col" className="pr-3">Category</th><th scope="col">Source / confidence</th></tr></thead>
                <tbody>{d.transactions.map((t) => (
                  <tr key={t.id} className="border-b border-slate-100 dark:border-slate-800"><td className="py-1 pr-3 whitespace-nowrap">{t.date}</td><td className="pr-3">{t.description}</td><td className="pr-3 text-right tabular-nums">{money(t.amount)} {t.direction === "credit" ? "cr" : "dr"}</td><td className="pr-3">{titleCase(t.category)}</td><td>{t.category_source} · {t.confidence}</td></tr>))}</tbody>
              </table>
            </div>
          </details>
        )}
      </section>

      <section aria-labelledby="mo-h" className="space-y-2">
        <h3 id="mo-h" className="text-lg font-semibold">Model output (separate from your decision)</h3>
        {a ? (
          <>
            <dl className="grid gap-x-6 gap-y-1 text-sm md:grid-cols-2">
              <dt className="text-slate-500">Model version</dt><dd className="break-all">{a.model_version}</dd>
              <dt className="text-slate-500">Feature schema</dt><dd>{a.feature_schema_version}</dd>
              <dt className="text-slate-500">Policy version</dt><dd>{a.policy_version}</dd>
              <dt className="text-slate-500">Policy recommendation</dt><dd className="font-semibold">{d.policy_recommendation ? label(d.policy_recommendation) : "—"}</dd>
            </dl>
            <ul className="text-sm">{a.policy_result.rules.map((r) => <li key={r.rule}>{r.passed ? "✓" : "✗"} {r.rule} ({(r.value * 100).toFixed(1)}% vs limit {(r.threshold * 100).toFixed(0)}%)</li>)}</ul>
            <PredictionResult result={a.result} />
          </>
        ) : <p className="text-sm">No official assessment.</p>}
      </section>

      {(d.info_requests.length > 0 || d.decisions.length > 0) && (
        <section aria-labelledby="hist-h" className="space-y-2">
          <h3 id="hist-h" className="text-lg font-semibold">Questions and decisions</h3>
          <ul className="space-y-2 text-sm">
            {d.info_requests.map((r) => <li key={`i${r.id}`} className="rounded border border-slate-200 p-2 dark:border-slate-700"><strong>You asked:</strong> {r.message}<br /><strong>Applicant answered:</strong> {r.response ?? "not yet"}</li>)}
            {d.decisions.map((x) => <li key={`d${x.id}`} className="rounded border border-slate-200 p-2 dark:border-slate-700"><strong>Decision:</strong> {label(x.decision)} — {x.reason}{x.is_override ? ` (OVERRIDE of ${label(x.policy_recommendation ?? "")}: ${x.override_reason})` : ""}</li>)}
          </ul>
        </section>
      )}

      {actionable ? (
        <section aria-labelledby="act-h" className="space-y-6 rounded-xl border border-slate-300 p-4 dark:border-slate-700">
          <h3 id="act-h" className="text-lg font-semibold">Your action</h3>
          {formError && <Notice tone="error" title="Check the form">{formError}</Notice>}
          {error && <Notice tone="error" title="That did not work">{error}</Notice>}
          <div className="space-y-2">
            <h4 className="font-semibold">Request more information</h4>
            <label htmlFor="rv-question" className="block text-sm">Question for the applicant</label>
            <textarea id="rv-question" rows={3} value={question} onChange={(e) => setQuestion(e.target.value)} className="w-full rounded-md border border-slate-300 bg-white p-2 text-sm dark:border-slate-700 dark:bg-slate-900" />
            <button type="button" disabled={busy !== null} onClick={() => send("info")} className="rounded-md border border-orange-700 px-4 py-2 text-sm font-medium text-orange-800 dark:text-orange-200">
              {busy === "info" ? "Sending…" : "Request information"}</button>
          </div>
          <div className="space-y-2 border-t border-slate-200 pt-4 dark:border-slate-700">
            <h4 className="font-semibold">Record a demonstration decision</h4>
            <p className="text-sm text-slate-600 dark:text-slate-300">Policy recommendation: <strong>{d.policy_recommendation ? label(d.policy_recommendation) : "—"}</strong>. Deciding differently is allowed but needs a written override reason.</p>
            <label htmlFor="rv-decision" className="block text-sm font-medium">Decision</label>
            <select id="rv-decision" value={decision} onChange={(e) => setDecision(e.target.value as typeof decision)} className="rounded-md border border-slate-300 bg-white px-2 py-1 text-sm dark:border-slate-700 dark:bg-slate-900">
              <option value="">Choose…</option><option value="demo_approved">Approve (demonstration)</option><option value="demo_declined">Decline (demonstration)</option>
            </select>
            <label htmlFor="rv-reason" className="block text-sm font-medium">Reasoning</label>
            <textarea id="rv-reason" rows={3} value={reason} onChange={(e) => setReason(e.target.value)} className="w-full rounded-md border border-slate-300 bg-white p-2 text-sm dark:border-slate-700 dark:bg-slate-900" />
            {needsOverride && (
              <div className="rounded-lg border border-amber-400 bg-amber-50 p-3 text-amber-950 dark:bg-amber-950 dark:text-amber-100">
                <label htmlFor="rv-override" className="block text-sm font-semibold">Override reason (required)</label>
                <p className="text-xs">Your decision differs from the policy recommendation. Explain why.</p>
                <textarea id="rv-override" rows={3} value={override} onChange={(e) => setOverride(e.target.value)} className="mt-1 w-full rounded-md border border-slate-300 bg-white p-2 text-sm text-slate-900" />
              </div>
            )}
            <button type="button" disabled={busy !== null} onClick={() => send("decision")} className="rounded-md bg-emerald-700 px-5 py-2 text-sm font-medium text-white hover:bg-emerald-800 disabled:opacity-60">
              {busy === "decision" ? "Recording…" : "Record decision"}</button>
          </div>
        </section>
      ) : (
        <Notice tone="info" title="No action available">This application is “{d.status.replace(/_/g, " ")}”, so decisions and questions are closed.</Notice>
      )}

      <section aria-labelledby="aud-h" className="space-y-2">
        <h3 id="aud-h" className="text-lg font-semibold">Audit history</h3>
        <ol className="space-y-1 text-sm">{d.timeline.map((e) => <li key={e.id}>{e.ts.replace("T", " ").replace("Z", "")} · {e.actor_role} · {e.action}{e.details.status_to ? ` → ${String(e.details.status_to)}` : ""}</li>)}</ol>
      </section>
    </div>
  );
}
