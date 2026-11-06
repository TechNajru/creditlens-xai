"use client";
import { useEffect, useState } from "react";
import { Bar, BarChart, CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { ApiError, getJson } from "@/lib/api";
import type { Evaluation } from "@/lib/types";
import { ExperimentsPanel } from "./ExperimentsPanel";
import { Notice, Spinner } from "./Notice";

type Track = "simulation" | "public";
type Result = { track: Track; data?: Evaluation; error?: string };
const TITLES: Record<Track, string> = { simulation: "Simulation model (synthetic data)", public: "Public-data model (UCI credit-card)" };

function Chart({ label, children }: { label: string; children: React.ReactNode }) {
  return <div role="img" aria-label={label} className="h-72 w-full">{children}</div>;
}

export function EvaluationDashboard() {
  const [track, setTrack] = useState<Track>("public");
  const [result, setResult] = useState<Result | null>(null);

  useEffect(() => {
    let cancelled = false;
    getJson<Evaluation>(`/api/v1/models/${track}/evaluation`)
      .then((data) => { if (!cancelled) setResult({ track, data }); })
      .catch((e) => {
        if (cancelled) return;
        const msg = e instanceof ApiError && e.status === 404
          ? "No evaluation report yet. Train the model first (python -m app.train or python -m app.public_train)."
          : e instanceof ApiError ? e.message : "Could not load the evaluation.";
        setResult({ track, error: msg });
      });
    return () => { cancelled = true; };
  }, [track]);

  const loading = !result || result.track !== track;
  const ev = !loading ? result?.data : undefined;
  const rep = ev?.report;
  const test = rep ? (rep.test_metrics ?? rep.test_metrics_selected) : undefined;
  const curve = rep?.calibration_curve_test.mean_predicted.map((x, i) => ({
    predicted: Number(x.toFixed(4)), observed: Number(rep.calibration_curve_test.fraction_positive[i].toFixed(4)), perfect: Number(x.toFixed(4)),
  }));
  const importance = rep?.global_importance?.values.slice(0, 10).map((v) => ({ feature: v.feature, value: Number(v.mean_abs_shap.toFixed(4)) }));

  return (
    <div className="space-y-6">
      <div role="tablist" aria-label="Model track" className="flex gap-2">
        {(["public", "simulation"] as Track[]).map((t) => (
          <button key={t} role="tab" aria-selected={track === t} onClick={() => setTrack(t)}
            className={`rounded-md border px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-sky-500 ${track === t ? "border-sky-700 bg-sky-700 text-white" : "border-slate-300 dark:border-slate-600"}`}>
            {TITLES[t]}
          </button>
        ))}
      </div>
      {loading && <Spinner label="Loading evaluation…" />}
      {!loading && result?.error && <Notice tone="error" title="Evaluation not available">{result.error}</Notice>}
      {rep && ev && test && (
        <div className="space-y-8">
          <Notice tone="warning" title="Read before interpreting">
            <p>{rep.data_provenance}. Fairness has not been assessed yet. These numbers describe one random hold-out and carry sampling uncertainty.</p>
          </Notice>
          <section aria-labelledby="sel-h">
            <h2 id="sel-h" className="text-lg font-semibold">Selected model</h2>
            <p className="text-sm">{rep.selected.model} with {rep.selected.calibration} calibration · <span className="break-all">{rep.model_version}</span></p>
            <p className="mt-1 text-sm text-slate-600 dark:text-slate-300">Chosen by lowest Brier score on the validation split. The test split was used once, afterwards. Very close scores between candidates are practical ties.</p>
          </section>
          <section aria-labelledby="test-h">
            <h2 id="test-h" className="text-lg font-semibold">Untouched test split (selected model)</h2>
            <dl className="mt-2 grid grid-cols-2 gap-3 md:grid-cols-4">
              {[["ROC-AUC", test.roc_auc], ["Average precision", test.average_precision], ["Brier score", test.brier], ["Log loss", test.log_loss]].map(([k, v]) => (
                <div key={k as string} className="rounded-lg border border-slate-200 p-3 dark:border-slate-700">
                  <dt className="text-xs text-slate-500">{k as string}</dt><dd className="text-xl font-semibold tabular-nums">{(v as number).toFixed(3)}</dd>
                </div>
              ))}
            </dl>
            <p className="mt-2 text-sm text-slate-600 dark:text-slate-300">
              Baseline that always predicts the average rate: Brier {rep.majority_baseline.brier_constant_base_rate.toFixed(3)}, log loss {rep.majority_baseline.log_loss_constant_base_rate.toFixed(3)}. Lower is better for both.
            </p>
          </section>
          <section aria-labelledby="cal-h">
            <h2 id="cal-h" className="text-lg font-semibold">Calibration (test split)</h2>
            <p className="text-sm text-slate-600 dark:text-slate-300">If predicted probabilities are trustworthy, the observed rate follows the dashed line. Good ranking does not guarantee good calibration.</p>
            <Chart label="Calibration curve: observed default rate against predicted probability">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={curve} margin={{ left: 8, right: 16, bottom: 22 }}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="predicted" type="number" domain={[0, 1]} label={{ value: "Predicted probability", position: "insideBottom", offset: -4 }} />
                  <YAxis domain={[0, 1]} />
                  <Tooltip /><Legend verticalAlign="top" height={28} />
                  <Line isAnimationActive={false} dataKey="perfect" name="Perfect calibration" stroke="#94a3b8" strokeDasharray="5 5" dot={false} />
                  <Line isAnimationActive={false} dataKey="observed" name="Observed" stroke="#0284c7" strokeWidth={2} />
                </LineChart>
              </ResponsiveContainer>
            </Chart>
          </section>
          <section aria-labelledby="thr-h">
            <h2 id="thr-h" className="text-lg font-semibold">Threshold trade-offs (experimental)</h2>
            <p className="text-sm text-slate-600 dark:text-slate-300">Flagging more clients as risky raises recall but lowers precision. No threshold here is a validated policy.</p>
            <Chart label="Precision, recall and F1 by threshold">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={rep.test_threshold_tradeoffs}>
                  <CartesianGrid strokeDasharray="3 3" /><XAxis dataKey="threshold" type="number" domain={[0, 0.5]} ticks={[0.05, 0.1, 0.15, 0.2, 0.3, 0.5]} /><YAxis domain={[0, 1]} /><Tooltip /><Legend verticalAlign="top" height={28} />
                  <Line isAnimationActive={false} dataKey="precision" stroke="#0284c7" /><Line isAnimationActive={false} dataKey="recall" stroke="#dc2626" /><Line isAnimationActive={false} dataKey="f1" stroke="#16a34a" />
                </LineChart>
              </ResponsiveContainer>
            </Chart>
          </section>
          <section aria-labelledby="cand-h">
            <h2 id="cand-h" className="text-lg font-semibold">Validation comparison (used for selection)</h2>
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <caption className="sr-only">Model and calibration candidates scored on the validation split</caption>
                <thead><tr className="border-b border-slate-300 dark:border-slate-700"><th scope="col" className="py-1 pr-3">Model</th><th scope="col" className="pr-3">Calibration</th><th scope="col" className="pr-3 text-right">Brier</th><th scope="col" className="pr-3 text-right">ROC-AUC</th><th scope="col" className="text-right">Log loss</th></tr></thead>
                <tbody>
                  {rep.validation_candidates.map((c) => {
                    const sel = c.model === rep.selected.model && c.calibration === rep.selected.calibration;
                    return (
                      <tr key={`${c.model}-${c.calibration}`} className={`border-b border-slate-100 dark:border-slate-800 ${sel ? "font-semibold" : ""}`}>
                        <td className="py-1 pr-3">{c.model}{sel ? " (selected)" : ""}</td><td className="pr-3">{c.calibration}</td>
                        <td className="pr-3 text-right tabular-nums">{c.brier.toFixed(4)}</td><td className="pr-3 text-right tabular-nums">{c.roc_auc.toFixed(3)}</td><td className="text-right tabular-nums">{c.log_loss.toFixed(4)}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </section>
          {importance && (
            <section aria-labelledby="imp-h">
              <h2 id="imp-h" className="text-lg font-semibold">Global feature importance (SHAP)</h2>
              <p className="text-sm text-slate-600 dark:text-slate-300">Mean absolute contribution to the model&apos;s raw risk score, on a sample of the validation split. It describes the model, not causes, and it is not the same as an individual explanation.</p>
              <Chart label="Top global feature importances">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={importance} layout="vertical" margin={{ left: 16 }}>
                    <XAxis type="number" /><YAxis type="category" dataKey="feature" width={150} tick={{ fontSize: 11 }} /><Tooltip />
                    <Bar isAnimationActive={false} dataKey="value" fill="#0284c7" />
                  </BarChart>
                </ResponsiveContainer>
              </Chart>
            </section>
          )}
          {track === "public" && <ExperimentsPanel />}
          <Notice tone="warning" title="Limitations">
            <ul className="list-disc space-y-1 pl-5">{ev.limitations.map((l) => <li key={l}>{l}</li>)}</ul>
          </Notice>
        </div>
      )}
    </div>
  );
}
