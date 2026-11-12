"use client";
import { useEffect, useState } from "react";
import { ApiError, getJson, postForm } from "@/lib/api";
import type { AnalyzeResponse, Categories, PreviewResponse } from "@/lib/types";
import { money, titleCase } from "@/lib/format";
import { Notice, Spinner } from "./Notice";
import { MonthlyChart } from "./MonthlyChart";

const MAX_BYTES = 2_000_000;

function Metric({ label, value, note }: { label: string; value: string; note?: string }) {
  return (
    <div className="rounded-lg border border-slate-200 p-3 dark:border-slate-700">
      <dt className="text-xs text-slate-500 dark:text-slate-400">{label}</dt>
      <dd className="text-lg font-semibold tabular-nums">{value}</dd>
      {note && <p className="mt-1 text-xs text-slate-500">{note}</p>}
    </div>
  );
}

export function Analysis({ a }: { a: AnalyzeResponse }) {
  const m = a.metrics;
  return (
    <section aria-labelledby="analysis-h" className="space-y-4">
      <h2 id="analysis-h" className="text-xl font-semibold">Cash-flow summary</h2>
      <Notice tone="info" title="Descriptive only">
        These figures describe the uploaded statement. They are {a.used_for_risk_model ? "" : "not "}used by any risk model.
      </Notice>
      {!a.coverage.sufficient_for_analysis && (
        <Notice tone="warning" title="Not enough data for reliable metrics">
          <ul className="list-disc pl-5">{a.coverage.reasons.map((r) => <li key={r}>{r}</li>)}</ul>
          <p className="mt-1">Unknown values are shown as unknown, never as zero. A human reviewer would be asked to check this case.</p>
        </Notice>
      )}
      <p className="text-sm text-slate-600 dark:text-slate-300">
        Statement {a.coverage.first_date ?? "?"} to {a.coverage.last_date ?? "?"}; usable interior months: {a.coverage.usable_interior_months ?? 0}.
        {a.coverage.note ? ` ${a.coverage.note}` : ""}
      </p>
      {a.monthly.length > 0 && <MonthlyChart monthly={a.monthly} />}
      {m ? (
        <dl className="grid gap-3 md:grid-cols-3">
          <Metric label="Avg monthly income (confirmed or likely)" value={money(m.avg_monthly_income_confirmed_or_likely)} note={`Confirmed only: ${money(m.avg_monthly_income_confirmed_only)}`} />
          <Metric label="Avg monthly unverified inflow (e.g. UPI)" value={money(m.avg_monthly_unverified_inflow)} note="Never counted as income." />
          <Metric label="Avg monthly outflow" value={money(m.avg_monthly_outflow)} />
          <Metric label="Avg monthly net cash flow" value={money(m.avg_monthly_net_cashflow)} />
          <Metric label="Months with negative net cash flow" value={`${m.negative_net_cashflow_months} of ${m.months_used}`} />
          <Metric label="Income variability (CV)" value={m.income_variability_cv === null ? "unknown" : m.income_variability_cv.toFixed(2)} note="Needs at least 3 usable months." />
          <Metric label="Avg essential spending" value={money(m.avg_monthly_essential_spend)} />
          <Metric label="Observed monthly debt payments" value={money(m.observed_monthly_debt_payments)} note={m.observed_debt_payments_note} />
          <Metric label="Observed debt-to-income" value={m.observed_debt_to_income === null ? "undefined" : `${(m.observed_debt_to_income * 100).toFixed(0)}%`} />
        </dl>
      ) : (
        <p className="text-sm text-slate-600 dark:text-slate-400">No metrics could be computed from this file.</p>
      )}
      <div className="text-sm">
        <p><strong>Identified recurring income:</strong> {a.identified_recurring_income_monthly ? money(a.identified_recurring_income_monthly) + " per month (uncertain, pattern-based)" : "none identified"}</p>
        <p><strong>Payment timeliness:</strong> {a.payment_timeliness?.computed ? `${((a.payment_timeliness.on_time_rate ?? 0) * 100).toFixed(0)}% on time (${a.payment_timeliness.n_obligations} obligations)` : "not computed — requires due dates and payment dates in the file"}</p>
        {a.missingness?.low_confidence_value_share != null && (
          <p><strong>Value in low-confidence categories:</strong> {(a.missingness.low_confidence_value_share * 100).toFixed(0)}%</p>
        )}
      </div>
    </section>
  );
}

export function CashflowWorkbench() {
  const [file, setFile] = useState<File | null>(null);
  const [fileError, setFileError] = useState<string | null>(null);
  const [categories, setCategories] = useState<Categories | null>(null);
  const [corrections, setCorrections] = useState<Record<string, string>>({});
  const [preview, setPreview] = useState<PreviewResponse | null>(null);
  const [analysis, setAnalysis] = useState<AnalyzeResponse | null>(null);
  const [busy, setBusy] = useState<null | "preview" | "analyze">(null);
  const [error, setError] = useState<string | null>(null);
  const [onlyUncertain, setOnlyUncertain] = useState(true);

  useEffect(() => {
    let cancelled = false;
    getJson<Categories>("/api/v1/transactions/categories")
      .then((c) => { if (!cancelled) setCategories(c); })
      .catch((e) => { if (!cancelled) setError(e instanceof ApiError ? e.message : "Could not load categories."); });
    return () => { cancelled = true; };
  }, []);

  function onFile(f: File | null) {
    setPreview(null); setAnalysis(null); setCorrections({}); setError(null); setFileError(null);
    if (!f) { setFile(null); return; }
    if (!f.name.toLowerCase().endsWith(".csv")) { setFile(null); setFileError("Only .csv files are accepted."); return; }
    if (f.size > MAX_BYTES) { setFile(null); setFileError("File is larger than 2 MB."); return; }
    setFile(f);
  }

  function formData(corr: Record<string, string>) {
    const fd = new FormData();
    fd.append("file", file as File);
    if (Object.keys(corr).length) fd.append("corrections", JSON.stringify(corr));
    return fd;
  }

  async function run(kind: "preview" | "analyze", corr = corrections) {
    if (!file) return;
    setBusy(kind); setError(null);
    try {
      if (kind === "preview") { setPreview(await postForm<PreviewResponse>("/api/v1/uploads/preview", formData(corr))); setAnalysis(null); }
      else setAnalysis(await postForm<AnalyzeResponse>("/api/v1/cashflow/analyze", formData(corr)));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Something went wrong. Please try again.");
    } finally { setBusy(null); }
  }

  const rows = preview?.transactions.filter((t) => !onlyUncertain || t.confidence !== "high" || corrections[t.key]) ?? [];
  const correctionCount = Object.keys(corrections).length;

  return (
    <div className="space-y-6">
      <Notice tone="info" title="Use fictional or de-identified data only">
        Sample files are in the repository&apos;s <code>sample_data</code> folder (all synthetic). Your file is processed by the API and is not stored in this version.
      </Notice>
      <div>
        <label htmlFor="csv-file" className="block text-sm font-medium">Transaction CSV (max 2 MB)</label>
        <input id="csv-file" type="file" accept=".csv,text/csv" onChange={(e) => onFile(e.target.files?.[0] ?? null)}
          aria-describedby="csv-help" className="mt-1 block w-full text-sm" />
        <p id="csv-help" className="mt-1 text-xs text-slate-500">Needs date, description and amount (plus direction, or signed amounts / separate debit and credit columns).</p>
        {fileError && <p role="alert" className="mt-1 text-sm font-medium text-red-700 dark:text-red-300">{fileError}</p>}
      </div>
      <div className="flex flex-wrap gap-3">
        <button type="button" disabled={!file || busy !== null} onClick={() => run("preview")}
          className="rounded-md bg-sky-700 px-4 py-2 text-sm font-medium text-white hover:bg-sky-800 disabled:opacity-50 focus:outline-none focus:ring-2 focus:ring-sky-500">
          {busy === "preview" ? "Reading…" : "Preview file"}
        </button>
        <button type="button" disabled={!file || busy !== null} onClick={() => run("analyze")}
          className="rounded-md border border-sky-700 px-4 py-2 text-sm font-medium text-sky-800 hover:bg-sky-50 disabled:opacity-50 focus:outline-none focus:ring-2 focus:ring-sky-500 dark:text-sky-200 dark:hover:bg-slate-800">
          {busy === "analyze" ? "Analysing…" : "Analyse cash flow"}
        </button>
      </div>
      {busy && <Spinner label={busy === "preview" ? "Reading and validating the file…" : "Computing the cash-flow summary…"} />}
      {error && <Notice tone="error" title="Could not process the file">{error}</Notice>}
      {!file && !preview && !analysis && !error && <p className="text-sm text-slate-600 dark:text-slate-400">No file selected yet.</p>}

      {preview && (
        <section aria-labelledby="preview-h" className="space-y-4">
          <h2 id="preview-h" className="text-xl font-semibold">Preview</h2>
          <p className="text-sm">
            {preview.stats.rows_valid} of {preview.stats.rows_total} rows are usable · {preview.stats.rows_with_errors} with errors · {preview.stats.duplicates_excluded} possible duplicates excluded · date format {preview.date_format ?? "not detected"}.
          </p>
          {preview.stats.rows_valid === 0 && <Notice tone="error" title="No usable rows">Fix the problems below and upload the file again.</Notice>}
          {preview.issues.length > 0 && (
            <details open className="rounded-lg border border-slate-200 p-3 dark:border-slate-700">
              <summary className="cursor-pointer text-sm font-semibold">Row problems ({preview.issues.length})</summary>
              <ul className="mt-2 space-y-1 text-sm">
                {preview.issues.map((i, idx) => (
                  <li key={idx}><span className="font-medium">{i.severity === "error" ? "Error" : "Warning"}</span> · data row {i.row} · {i.field}: {i.problem}</li>
                ))}
              </ul>
            </details>
          )}
          {preview.category_issues.length > 0 && (
            <Notice tone="warning" title="Category notes">
              <ul className="list-disc pl-5">{preview.category_issues.map((c, i) => <li key={i}>{c.row ? `Row ${c.row}: ` : c.key ? `${c.key}: ` : ""}{c.problem}</li>)}</ul>
            </Notice>
          )}
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={onlyUncertain} onChange={(e) => setOnlyUncertain(e.target.checked)} />
            Show only uncertain rows (guessed categories you may want to correct)
          </label>
          {rows.length === 0 ? (
            <p className="text-sm text-slate-600 dark:text-slate-400">{onlyUncertain ? "No uncertain rows — untick the box to see every row." : "No transactions to show."}</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <caption className="sr-only">Transactions with category and confidence</caption>
                <thead><tr className="border-b border-slate-300 dark:border-slate-700">
                  <th scope="col" className="py-1 pr-3">Date</th><th scope="col" className="pr-3">Description</th>
                  <th scope="col" className="pr-3 text-right">Amount</th><th scope="col" className="pr-3">Type</th>
                  <th scope="col" className="pr-3">Category</th><th scope="col">Source / confidence</th>
                </tr></thead>
                <tbody>
                  {rows.map((t) => {
                    const options = categories ? (t.direction === "credit" ? categories.credit : categories.debit) : [];
                    return (
                      <tr key={t.key} className="border-b border-slate-100 dark:border-slate-800">
                        <td className="py-1 pr-3 whitespace-nowrap">{t.date}</td><td className="pr-3">{t.description}</td>
                        <td className="pr-3 text-right tabular-nums">{money(t.amount)}</td><td className="pr-3">{t.direction}</td>
                        <td className="pr-3">
                          <select aria-label={`Category for row ${t.row}`} disabled={!categories}
                            value={corrections[t.key] ?? t.category}
                            onChange={(e) => setCorrections((c) => {
                              const next = { ...c };
                              if (e.target.value === t.category) delete next[t.key]; else next[t.key] = e.target.value;
                              return next;
                            })}
                            className="rounded border border-slate-300 bg-white px-1 py-0.5 text-sm dark:border-slate-600 dark:bg-slate-900">
                            {options.map((o) => <option key={o} value={o}>{titleCase(o)}</option>)}
                          </select>
                        </td>
                        <td>{corrections[t.key] ? "your correction" : t.category_source} · {corrections[t.key] ? "high" : t.confidence}{!corrections[t.key] && t.confidence === "low" ? " (guess)" : ""}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
          {preview.truncated && <p className="text-xs text-slate-500">Only the first 200 rows are shown; all rows are used in the analysis.</p>}
          {correctionCount > 0 && (
            <button type="button" disabled={busy !== null} onClick={() => run("preview")}
              className="rounded-md border border-slate-400 px-3 py-1 text-sm hover:bg-slate-100 dark:hover:bg-slate-800">
              Apply {correctionCount} correction{correctionCount === 1 ? "" : "s"} and refresh preview
            </button>
          )}
        </section>
      )}
      {analysis && <Analysis a={analysis} />}
    </div>
  );
}
