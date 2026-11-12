"use client";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { ApiError, deleteReq, getJson, patchJson, postForm, postJson } from "@/lib/api";
import { LOAN_CONFIG, LOAN_FIELDS, validateFields } from "@/lib/fields";
import type { AnalyzeResponse, ApplicantApplication, TransactionsResponse, UploadResponse } from "@/lib/types";
import { titleCase } from "@/lib/format";
import { Analysis } from "./CashflowWorkbench";
import { NumberField } from "./NumberField";
import { Notice, Spinner } from "./Notice";
import { PredictionResult } from "./PredictionResult";
import { StatusBadge } from "./StatusBadge";

const MAX_BYTES = 2_000_000;
type Bundle = { app: ApplicantApplication; txs: TransactionsResponse | null; cashflow: AnalyzeResponse | null };

async function fetchAll(id: string): Promise<Bundle> {
  const app = await getJson<ApplicantApplication>(`/api/v1/applications/${id}`);
  if (!app.upload) return { app, txs: null, cashflow: null };
  const [txs, cashflow] = await Promise.all([
    getJson<TransactionsResponse>(`/api/v1/applications/${id}/transactions`),
    getJson<AnalyzeResponse>(`/api/v1/applications/${id}/cashflow`).catch(() => null),
  ]);
  return { app, txs, cashflow };
}

const toStrings = (inputs: Record<string, number | null>) =>
  Object.fromEntries(Object.entries(inputs).map(([k, v]) => [k, v === null ? "" : String(v)]));

export function ApplicationWorkflow({ id }: { id?: string }) {
  const router = useRouter();
  const [data, setData] = useState<Bundle | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [values, setValues] = useState<Record<string, string>>({});
  const [unknown, setUnknown] = useState<Record<string, boolean>>({});
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const [confirm, setConfirm] = useState(false);
  const [onlyUncertain, setOnlyUncertain] = useState(true);
  const [reply, setReply] = useState<Record<number, string>>({});
  const [confirmDelete, setConfirmDelete] = useState(false);

  function apply(b: Bundle) {
    setData(b);
    setValues(toStrings(b.app.loan_inputs));
    setUnknown({ credit_history_months: b.app.loan_inputs.credit_history_months === null });
  }

  useEffect(() => {
    if (!id) return;
    let cancelled = false;
    fetchAll(id)
      .then((b) => { if (!cancelled) apply(b); })
      .catch((e) => { if (!cancelled) setLoadError(e instanceof ApiError ? e.message : "Could not load this application."); });
    return () => { cancelled = true; };
  }, [id]);

  async function act<T>(label: string, fn: () => Promise<T>, after?: (r: T) => void) {
    setBusy(label); setError(null); setInfo(null);
    try {
      const r = await fn();
      if (after) after(r);
      return r;
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Something went wrong. Please try again.");
    } finally { setBusy(null); }
  }

  const reload = async () => { if (id) apply(await fetchAll(id)); };
  const app = data?.app;
  const editable = !id || (app?.editable ?? false);

  async function saveDetails() {
    const v = validateFields(LOAN_FIELDS, values, unknown);
    setErrors(v.errors);
    if (!v.ok) return;
    await act("save", async () => {
      if (!id) {
        const created = await postJson<ApplicantApplication>("/api/v1/applications", v.payload);
        router.replace(`/applications/${created.id}`);
      } else {
        await patchJson(`/api/v1/applications/${id}`, v.payload);
        await reload();
        setInfo("Details saved. Any earlier preview was discarded because it no longer matches.");
      }
    });
  }

  async function onFile(f: File | null) {
    setError(null);
    if (!f || !id) return;
    if (!f.name.toLowerCase().endsWith(".csv")) { setError("Only .csv files are accepted."); return; }
    if (f.size > MAX_BYTES) { setError("File is larger than 2 MB."); return; }
    const fd = new FormData();
    fd.append("file", f);
    await act("upload", async () => {
      const r = await postForm<UploadResponse>(`/api/v1/applications/${id}/uploads`, fd);
      await reload();
      setInfo(`${r.upload.rows_valid} of ${r.upload.rows_total} rows were usable.`);
    });
  }

  const correct = (txId: number, category: string) =>
    act("correct", async () => { await patchJson(`/api/v1/applications/${id}/transactions/${txId}`, { category }); await reload(); });
  const preview = () => act("preview", async () => { await postJson(`/api/v1/applications/${id}/assessments/preview`, {}); await reload(); });
  const submit = () => act("submit", async () => { await postJson(`/api/v1/applications/${id}/submit`, {}); setConfirm(false); await reload(); });
  const respond = (rid: number) => act("respond", async () => {
    await postJson(`/api/v1/applications/${id}/info-requests/${rid}/respond`, { message: reply[rid] ?? "" });
    await reload();
  });
  const remove = () => act("delete", async () => { await deleteReq(`/api/v1/applications/${id}`); router.push("/dashboard"); });

  if (id && !data && !loadError) return <Spinner label="Loading application…" />;
  if (loadError) return <Notice tone="error" title="Could not open this application">{loadError}</Notice>;

  const uncertain = data?.txs?.transactions.filter((t) => !onlyUncertain || t.confidence !== "high") ?? [];
  const pending = app?.info_requests.filter((r) => r.responded_at === null) ?? [];
  const optionsFor = (dir: "credit" | "debit") => (dir === "credit" ? data?.txs?.credit_categories : data?.txs?.debit_categories) ?? [];

  return (
    <div className="space-y-8">
      {app && (
        <header className="flex flex-wrap items-center gap-3">
          <StatusBadge status={app.status} />
          <span className="text-sm text-slate-600 dark:text-slate-300">Created {app.created_at.slice(0, 10)}</span>
        </header>
      )}
      {app && !app.editable && (
        <Notice tone="info" title="This application is locked">
          {app.status === "final_demo_decision" ? "A reviewer has recorded a demonstration decision." : "It is with a reviewer, so it cannot be changed right now."}
        </Notice>
      )}
      {error && <Notice tone="error" title="That did not work">{error}</Notice>}
      {info && <Notice tone="success" title="Done">{info}</Notice>}

      {app?.status === "final_demo_decision" && app.final_decision && (
        <section aria-labelledby="dec-h" className="rounded-xl border border-emerald-300 bg-emerald-50 p-4 text-emerald-950 dark:border-emerald-800 dark:bg-emerald-950 dark:text-emerald-100">
          <h2 id="dec-h" className="font-semibold">Demonstration decision: {app.final_decision.decision.replace("demo_", "")}</h2>
          <p className="mt-1 text-sm">Reviewer&apos;s reasoning: {app.final_decision.reason}</p>
          <p className="mt-1 text-xs">This is a demonstration outcome in an educational prototype. It is not a real lending decision.</p>
        </section>
      )}

      {pending.map((r) => (
        <section key={r.id} aria-label="Reviewer question" className="space-y-2 rounded-xl border border-orange-300 bg-orange-50 p-4 text-orange-950 dark:border-orange-800 dark:bg-orange-950 dark:text-orange-100">
          <h2 className="font-semibold">The reviewer asked for more information</h2>
          <p className="text-sm">{r.message}</p>
          <label htmlFor={`reply-${r.id}`} className="block text-sm font-medium">Your answer</label>
          <textarea id={`reply-${r.id}`} rows={3} value={reply[r.id] ?? ""} onChange={(e) => setReply((s) => ({ ...s, [r.id]: e.target.value }))}
            className="w-full rounded-md border border-slate-300 bg-white p-2 text-sm text-slate-900" />
          <button type="button" disabled={busy !== null || !(reply[r.id] ?? "").trim()} onClick={() => respond(r.id)}
            className="rounded-md bg-orange-700 px-4 py-2 text-sm font-medium text-white disabled:opacity-50">Send answer</button>
          <p className="text-xs">After answering you can edit your details and submit again.</p>
        </section>
      ))}

      <section aria-labelledby="det-h" className="space-y-3">
        <h2 id="det-h" className="text-xl font-semibold">1. Loan details</h2>
        {!id && (
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-sm text-slate-600 dark:text-slate-300">Fictional examples:</span>
            {LOAN_CONFIG.examples.map((ex) => (
              <button key={ex.label} type="button" onClick={() => { setValues(ex.values); setUnknown({ credit_history_months: (ex.values.credit_history_months ?? "") === "" }); setErrors({}); }}
                className="rounded-md border border-slate-300 px-3 py-1 text-sm hover:bg-slate-100 dark:border-slate-600 dark:hover:bg-slate-800">{ex.label}</button>
            ))}
          </div>
        )}
        <div className="grid gap-4 md:grid-cols-2">
          {LOAN_FIELDS.map((f) => (
            <div key={f.name}>
              <NumberField id={`app-${f.name}`} label={f.label} hint={f.hint} value={values[f.name] ?? ""} error={errors[f.name]}
                disabled={!editable || (f.optional && unknown[f.name])} onChange={(v) => setValues((s) => ({ ...s, [f.name]: v }))} />
              {f.optional && (
                <label className="mt-1 flex items-center gap-2 text-sm">
                  <input type="checkbox" disabled={!editable} checked={!!unknown[f.name]} onChange={(e) => setUnknown((s) => ({ ...s, [f.name]: e.target.checked }))} />
                  Unknown / not available
                </label>
              )}
            </div>
          ))}
        </div>
        {Object.keys(errors).length > 0 && <Notice tone="error" title="Please fix the highlighted fields">{Object.keys(errors).length} field(s) need attention.</Notice>}
        {editable && (
          <button type="button" disabled={busy !== null} onClick={saveDetails}
            className="rounded-md bg-sky-700 px-5 py-2 text-sm font-medium text-white hover:bg-sky-800 disabled:opacity-60">
            {busy === "save" ? "Saving…" : id ? "Save details" : "Create draft"}
          </button>
        )}
      </section>

      {id && app && (
        <>
          <section aria-labelledby="up-h" className="space-y-3">
            <h2 id="up-h" className="text-xl font-semibold">2. Transactions (optional)</h2>
            <p className="text-sm text-slate-600 dark:text-slate-300">Upload a fictional or de-identified CSV. It is used for the cash-flow summary and shown to the reviewer; it is <strong>not</strong> an input to the risk model.</p>
            {app.editable && (
              <div>
                <label htmlFor="tx-file" className="block text-sm font-medium">Transaction CSV (max 2 MB)</label>
                <input id="tx-file" type="file" accept=".csv,text/csv" disabled={busy !== null} onChange={(e) => onFile(e.target.files?.[0] ?? null)} className="mt-1 block text-sm" />
              </div>
            )}
            {busy === "upload" && <Spinner label="Reading and validating the file…" />}
            {app.upload ? (
              <div className="space-y-3">
                <p className="text-sm">{app.upload.filename}: {app.upload.rows_valid} of {app.upload.rows_total} rows usable · {app.upload.rows_with_errors} with errors · {app.upload.duplicates_excluded} duplicates excluded.</p>
                {app.upload.issues.length > 0 && (
                  <details className="rounded-lg border border-slate-200 p-3 dark:border-slate-700">
                    <summary className="cursor-pointer text-sm font-semibold">Row problems ({app.upload.issues.length})</summary>
                    <ul className="mt-2 space-y-1 text-sm">{app.upload.issues.map((i, k) => <li key={k}>{i.severity === "error" ? "Error" : "Warning"} · data row {i.row} · {i.field}: {i.problem}</li>)}</ul>
                  </details>
                )}
                <label className="flex items-center gap-2 text-sm">
                  <input type="checkbox" checked={onlyUncertain} onChange={(e) => setOnlyUncertain(e.target.checked)} /> Show only uncertain rows (guessed categories to check)
                </label>
                {uncertain.length === 0 ? (
                  <p className="text-sm text-slate-600 dark:text-slate-400">{onlyUncertain ? "No uncertain rows. Untick the box to see every row." : "No transactions."}</p>
                ) : (
                  <div className="overflow-x-auto">
                    <table className="w-full text-left text-sm">
                      <caption className="sr-only">Transactions with categories</caption>
                      <thead><tr className="border-b border-slate-300 dark:border-slate-700">
                        <th scope="col" className="py-1 pr-3">Date</th><th scope="col" className="pr-3">Description</th><th scope="col" className="pr-3 text-right">Amount</th>
                        <th scope="col" className="pr-3">Type</th><th scope="col" className="pr-3">Category</th><th scope="col">Source / confidence</th>
                      </tr></thead>
                      <tbody>
                        {uncertain.map((t) => (
                          <tr key={t.id} className="border-b border-slate-100 dark:border-slate-800">
                            <td className="py-1 pr-3 whitespace-nowrap">{t.date}</td><td className="pr-3">{t.description}</td>
                            <td className="pr-3 text-right tabular-nums">{t.amount.toLocaleString("en-IN")}</td><td className="pr-3">{t.direction}</td>
                            <td className="pr-3">
                              {app.editable ? (
                                <select aria-label={`Category for row ${t.row}`} value={t.category} disabled={busy !== null} onChange={(e) => correct(t.id, e.target.value)}
                                  className="rounded border border-slate-300 bg-white px-1 py-0.5 text-sm dark:border-slate-600 dark:bg-slate-900">
                                  {optionsFor(t.direction).map((o) => <option key={o} value={o}>{titleCase(o)}</option>)}
                                </select>
                              ) : titleCase(t.category)}
                            </td>
                            <td>{t.category_source} · {t.confidence}{t.confidence === "low" ? " (guess)" : ""}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            ) : <p className="text-sm text-slate-600 dark:text-slate-400">No file uploaded.</p>}
          </section>

          {data?.cashflow && (
            <section aria-labelledby="cf-sum-h" className="space-y-3">
              <h2 id="cf-sum-h" className="text-xl font-semibold">3. Cash-flow summary</h2>
              <Analysis a={data.cashflow} />
            </section>
          )}

          <section aria-labelledby="as-h" className="space-y-3">
            <h2 id="as-h" className="text-xl font-semibold">4. Model assessment and explanation</h2>
            {app.editable && (
              <button type="button" disabled={busy !== null} onClick={preview}
                className="rounded-md border border-sky-700 px-4 py-2 text-sm font-medium text-sky-800 hover:bg-sky-50 disabled:opacity-60 dark:text-sky-200 dark:hover:bg-slate-800">
                {busy === "preview" ? "Assessing…" : "Run a preview assessment"}
              </button>
            )}
            {busy === "preview" && <Spinner label="Running the model and computing the explanation…" />}
            {app.assessment ? (
              <>
                <p className="text-sm text-slate-600 dark:text-slate-300">
                  {app.assessment.is_preview ? "Preview only: it is not sent to the reviewer until you submit." : "Official assessment recorded at submission and shown to the reviewer."}
                  {" "}Model {app.assessment.model_version} · policy {app.assessment.policy_version}.
                </p>
                <PredictionResult result={app.assessment.result} />
                <p className="text-sm"><strong>Demonstration policy:</strong> {app.assessment.policy_result.passes ? "all rules met" : "not all rules met"} (experimental thresholds, not a lending policy).</p>
              </>
            ) : <p className="text-sm text-slate-600 dark:text-slate-400">No assessment yet.</p>}
          </section>

          {app.editable && (
            <section aria-labelledby="sub-h" className="space-y-3 rounded-xl border border-slate-200 p-4 dark:border-slate-700">
              <h2 id="sub-h" className="text-xl font-semibold">5. Submit for human review</h2>
              <p className="text-sm text-slate-600 dark:text-slate-300">On submission the system validates your inputs, records an official assessment and sends the case to a human reviewer. You can no longer edit it until the reviewer responds.</p>
              <label className="flex items-start gap-2 text-sm">
                <input type="checkbox" className="mt-1" checked={confirm} onChange={(e) => setConfirm(e.target.checked)} />
                <span>I understand this is a demonstration, uses fictional or de-identified data, and does not create a real loan decision.</span>
              </label>
              <button type="button" disabled={!confirm || busy !== null || pending.length > 0} onClick={submit}
                className="rounded-md bg-emerald-700 px-5 py-2 text-sm font-medium text-white hover:bg-emerald-800 disabled:opacity-50">
                {busy === "submit" ? "Submitting…" : app.status === "info_requested" ? "Resubmit for review" : "Submit for review"}
              </button>
              {pending.length > 0 && <p className="text-xs text-slate-600">Answer the reviewer&apos;s question above before resubmitting.</p>}
            </section>
          )}

          <section aria-labelledby="tl-h" className="space-y-2">
            <h2 id="tl-h" className="text-xl font-semibold">History</h2>
            <ol className="space-y-1 text-sm">
              {app.timeline.map((e, i) => (
                <li key={i}>{e.ts.replace("T", " ").replace("Z", "")} · {titleCase(e.action.replace(".", " "))}{e.details.status_to ? ` → ${String(e.details.status_to)}` : ""}</li>
              ))}
            </ol>
          </section>

          {(app.status === "draft" || app.status === "info_requested" || app.status === "final_demo_decision") && (
            <section aria-labelledby="del-h" className="space-y-2 border-t border-slate-200 pt-4 dark:border-slate-700">
              <h2 id="del-h" className="text-base font-semibold">Delete this application</h2>
              <p className="text-sm text-slate-600 dark:text-slate-300">Removes the application, uploaded transactions and assessments. A minimal audit record (event type, time, ids; no financial content) is kept.</p>
              {!confirmDelete ? (
                <button type="button" onClick={() => setConfirmDelete(true)} className="rounded-md border border-red-600 px-3 py-1 text-sm text-red-700 dark:text-red-300">Delete…</button>
              ) : (
                <div className="flex gap-3">
                  <button type="button" disabled={busy !== null} onClick={remove} className="rounded-md bg-red-700 px-3 py-1 text-sm font-medium text-white">Yes, delete permanently</button>
                  <button type="button" onClick={() => setConfirmDelete(false)} className="rounded-md border border-slate-400 px-3 py-1 text-sm">Cancel</button>
                </div>
              )}
            </section>
          )}
        </>
      )}
    </div>
  );
}
