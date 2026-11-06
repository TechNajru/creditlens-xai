import type { PredictionResponse } from "@/lib/types";
import { pct, titleCase } from "@/lib/format";
import { ExplanationPanel } from "./ExplanationPanel";
import { Notice } from "./Notice";

export function PredictionResult({ result }: { result: PredictionResponse }) {
  const isPublic = result.model_track === "public_uci_credit_card";
  const p = result.default_probability_simulated ?? result.default_probability_next_month;
  const heading = isPublic ? "Estimated probability of credit-card payment default next month" : "Simulated default probability (synthetic model)";
  return (
    <section aria-labelledby="result-heading" aria-live="polite" className="space-y-5 rounded-xl border border-slate-200 p-5 dark:border-slate-700">
      <div>
        <h2 id="result-heading" className="text-sm font-medium text-slate-600 dark:text-slate-300">{heading}</h2>
        <p className="mt-1 text-4xl font-bold tabular-nums">{p === undefined ? "—" : pct(p)}</p>
        <p className="mt-2 text-sm text-slate-600 dark:text-slate-300">
          This is the model&apos;s calibrated estimate under the dataset&apos;s own definition of default. It is <strong>not</strong> a
          loan-approval probability, not a credit score, and not a prediction of what any real lender would decide.
        </p>
      </div>
      <dl className="grid gap-x-6 gap-y-1 text-sm md:grid-cols-2">
        <dt className="text-slate-500">Data provenance</dt><dd>{result.data_provenance}</dd>
        <dt className="text-slate-500">Model version</dt><dd className="break-all">{result.model_version}</dd>
        <dt className="text-slate-500">Calibration</dt>
        <dd>{result.calibration_evaluated ? `evaluated (${result.calibration_method})` : "not evaluated"}</dd>
        <dt className="text-slate-500">Raw model score (before calibration)</dt><dd className="tabular-nums">{result.uncalibrated_model_score.toFixed(4)}</dd>
      </dl>
      <div>
        <h3 className="text-sm font-semibold">Values calculated from your inputs</h3>
        <ul className="mt-1 grid gap-1 text-sm md:grid-cols-2">
          {Object.entries(result.derived_values).map(([k, v]) => (
            <li key={k}>{titleCase(k)}: <span className="font-medium">{v === null ? "undefined (not treated as zero)" : typeof v === "number" ? (Number.isInteger(v) ? v : v.toFixed(3)) : v ? "yes" : "no"}</span></li>
          ))}
        </ul>
      </div>
      <ExplanationPanel explanation={result.explanation} />
      <Notice tone="warning" title="Limitations">
        <ul className="list-disc space-y-1 pl-5">{result.limitations.map((l) => <li key={l}>{l}</li>)}</ul>
      </Notice>
    </section>
  );
}
