import type { Contribution, Explanation } from "@/lib/types";
import { signed } from "@/lib/format";
import { Notice } from "./Notice";
import { ContributionChart } from "./ContributionChart";

function FactorList({ title, items, empty }: { title: string; items: Contribution[]; empty: string }) {
  return (
    <section aria-label={title}>
      <h4 className="text-sm font-semibold">{title}</h4>
      {items.length === 0 ? (
        <p className="mt-1 text-sm text-slate-600 dark:text-slate-400">{empty}</p>
      ) : (
        <ul className="mt-1 space-y-1 text-sm">
          {items.map((c) => (
            <li key={c.feature} className="flex justify-between gap-3 rounded border border-slate-200 px-2 py-1 dark:border-slate-700">
              <span>{c.label}: <span className="font-medium">{c.value_display}</span></span>
              <span className="tabular-nums" aria-label={`contribution ${signed(c.contribution)}`}>{signed(c.contribution)}</span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

export function ExplanationPanel({ explanation }: { explanation: Explanation }) {
  if (explanation.status === "unavailable") {
    return (
      <Notice tone="warning" title="Explanation unavailable">
        {explanation.reason} The prediction above is unaffected, but no explanation is shown because none could be produced reliably.
      </Notice>
    );
  }
  const ex = explanation;
  return (
    <div className="space-y-4">
      <h3 className="text-lg font-semibold">Why the model gave this result</h3>
      {ex.reason_codes.length === 0 ? (
        <p className="text-sm text-slate-600 dark:text-slate-400">No single input moved the model&apos;s score noticeably for this case.</p>
      ) : (
        <ul className="list-disc space-y-1 pl-5 text-sm">{ex.reason_codes.map((r) => <li key={r}>{r}</li>)}</ul>
      )}
      <div className="grid gap-4 md:grid-cols-2">
        <FactorList title="Factors raising the model's risk score" items={ex.top_risk_increasing} empty="None found for this case." />
        <FactorList title="Factors lowering the model's risk score" items={ex.top_risk_reducing} empty="None found for this case." />
      </div>
      <Notice tone="info" title="How to read this">
        <ul className="list-disc space-y-1 pl-5">{ex.notes.map((n) => <li key={n}>{n}</li>)}</ul>
        <p className="mt-1">Numbers are on the scale of the <em>{ex.scale}</em>. They are not percentage-point changes.</p>
      </Notice>
      {ex.contributions && (
        <details className="rounded-lg border border-slate-200 p-3 dark:border-slate-700">
          <summary className="cursor-pointer text-sm font-semibold">Technical details (reviewer view)</summary>
          <dl className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1 text-sm md:grid-cols-4">
            <dt className="text-slate-500">Baseline score</dt><dd className="tabular-nums">{ex.baseline.toFixed(4)}</dd>
            <dt className="text-slate-500">Model raw score</dt><dd className="tabular-nums">{ex.model_output.toFixed(4)}</dd>
            <dt className="text-slate-500">Method</dt><dd>{ex.method}</dd>
            <dt className="text-slate-500">Version</dt><dd>{ex.version} (shap {ex.shap_version})</dd>
          </dl>
          <div className="mt-3"><ContributionChart items={ex.contributions} /></div>
          <div className="mt-3 overflow-x-auto">
            <table className="w-full text-left text-sm">
              <caption className="sr-only">All feature contributions</caption>
              <thead><tr className="border-b border-slate-300 dark:border-slate-700"><th scope="col" className="py-1 pr-3">Feature</th><th scope="col" className="pr-3">Value</th><th scope="col" className="text-right">Contribution</th></tr></thead>
              <tbody>
                {ex.contributions.map((c) => (
                  <tr key={c.feature} className="border-b border-slate-100 dark:border-slate-800">
                    <td className="py-1 pr-3">{c.label}</td><td className="pr-3">{c.value_display}</td>
                    <td className="text-right tabular-nums">{signed(c.contribution, 4)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {ex.global_importance && (
            <p className="mt-3 text-xs text-slate-500">
              Global importance (mean absolute contribution, {ex.global_importance.computed_on}) is shown on the Models page. A feature that matters globally may not matter for this individual case, and the reverse.
            </p>
          )}
        </details>
      )}
    </div>
  );
}
