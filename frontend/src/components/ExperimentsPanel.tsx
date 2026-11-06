"use client";
import { useEffect, useState } from "react";
import { ApiError, getJson } from "@/lib/api";
import type { ExperimentsReport } from "@/lib/types";
import { Notice, Spinner } from "./Notice";

export function ExperimentsPanel() {
  const [state, setState] = useState<{ data?: ExperimentsReport; error?: string } | null>(null);
  useEffect(() => {
    let cancelled = false;
    getJson<ExperimentsReport>("/api/v1/models/public/experiments")
      .then((data) => { if (!cancelled) setState({ data }); })
      .catch((e) => {
        if (cancelled) return;
        setState({ error: e instanceof ApiError && e.status === 404
          ? "Experiments not generated yet. Run: python -m app.experiments"
          : e instanceof ApiError ? e.message : "Could not load the experiments." });
      });
    return () => { cancelled = true; };
  }, []);

  return (
    <section aria-labelledby="exp-h" className="space-y-3">
      <h2 id="exp-h" className="text-lg font-semibold">Limited-information experiments</h2>
      {!state && <Spinner label="Loading experiments…" />}
      {state?.error && <Notice tone="info" title="Not available">{state.error}</Notice>}
      {state?.data && (() => {
        const d = state.data;
        return (
          <>
            <Notice tone="warning" title="Experiment, not thin-file lending">{d.label}</Notice>
            <p className="text-sm text-slate-600 dark:text-slate-300">
              Same split and fixed recipe for each variant ({d.recipe}); {d.n_test.toLocaleString("en-IN")} test clients. Constant base-rate Brier: {d.baseline_constant_brier.toFixed(4)} (lower is better; a model close to this has little skill).
            </p>
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <caption className="sr-only">Model performance when payment history is hidden</caption>
                <thead><tr className="border-b border-slate-300 dark:border-slate-700">
                  <th scope="col" className="py-1 pr-3">History visible to the model</th><th scope="col" className="pr-3 text-right">Features</th>
                  <th scope="col" className="pr-3 text-right">ROC-AUC (95% CI)</th><th scope="col" className="pr-3 text-right">Change vs full</th>
                  <th scope="col" className="pr-3 text-right">Brier</th><th scope="col" className="text-right">Calibration error</th>
                </tr></thead>
                <tbody>{d.variants.map((v) => (
                  <tr key={v.months_visible} className="border-b border-slate-100 dark:border-slate-800">
                    <th scope="row" className="py-1 pr-3 text-left font-normal">{v.label}</th>
                    <td className="pr-3 text-right tabular-nums">{v.n_features}</td>
                    <td className="pr-3 text-right tabular-nums">{v.roc_auc.toFixed(3)} ({v.roc_auc_ci95[0].toFixed(3)}–{v.roc_auc_ci95[1].toFixed(3)})</td>
                    <td className="pr-3 text-right tabular-nums">{v.roc_auc_change_vs_full === 0 ? "—" : v.roc_auc_change_vs_full.toFixed(3)}</td>
                    <td className="pr-3 text-right tabular-nums">{v.brier.toFixed(4)}</td><td className="text-right tabular-nums">{v.ece.toFixed(4)}</td>
                  </tr>))}</tbody>
              </table>
            </div>
            <ul className="list-disc space-y-1 pl-5 text-sm text-slate-600 dark:text-slate-300">{d.caveats.map((c) => <li key={c}>{c}</li>)}</ul>
          </>
        );
      })()}
    </section>
  );
}
