import type { ScenarioEval, ScenarioResult } from "@/lib/types";
import { money, pct } from "@/lib/format";

interface Column { title: string; ev: ScenarioEval | ScenarioResult; isBase?: boolean }

const changedOf = (c: Column) => ("changed_inputs" in c.ev ? c.ev.changed_inputs : {});
const hypoOf = (c: Column) => ("hypothetical" in c.ev ? c.ev.hypothetical : []);

export function ScenarioTable({ columns }: { columns: Column[] }) {
  const base = columns[0].ev;
  const inputRow = (label: string, field: "loan_amount" | "tenure_months" | "annual_interest_rate" | "existing_emi", fmt: (n: number) => string) => (
    <tr key={field} className="border-b border-slate-100 dark:border-slate-800">
      <th scope="row" className="py-1 pr-3 text-left font-normal">{label}</th>
      {columns.map((c) => {
        const changed = field in changedOf(c);
        return (
          <td key={c.title} className={`pr-3 tabular-nums ${changed ? "font-semibold" : ""}`}>
            {fmt(c.ev.inputs[field] as number)}
            {changed && <span className="ml-1 text-xs">(changed)</span>}
            {changed && hypoOf(c).includes(field) && <span className="ml-1 text-xs">(hypothetical)</span>}
          </td>
        );
      })}
    </tr>
  );
  const metricRow = (label: string, get: (m: ScenarioEval["metrics"]) => string) => (
    <tr key={label} className="border-b border-slate-100 dark:border-slate-800">
      <th scope="row" className="py-1 pr-3 text-left font-normal">{label}</th>
      {columns.map((c) => <td key={c.title} className="pr-3 tabular-nums">{get(c.ev.metrics)}</td>)}
    </tr>
  );
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-sm">
        <caption className="sr-only">Comparison of the base application and scenarios</caption>
        <thead>
          <tr className="border-b border-slate-300 dark:border-slate-700">
            <th scope="col" className="py-1 pr-3">Input / result</th>
            {columns.map((c) => <th key={c.title} scope="col" className="pr-3">{c.title}</th>)}
          </tr>
        </thead>
        <tbody>
          {inputRow("Loan amount", "loan_amount", (n) => money(n))}
          {inputRow("Tenure (months)", "tenure_months", (n) => String(n))}
          {inputRow("Interest rate", "annual_interest_rate", (n) => `${n}%`)}
          {inputRow("Existing monthly EMI", "existing_emi", (n) => money(n))}
          {metricRow("EMI of this loan (recalculated)", (m) => money(m.new_loan_emi))}
          {metricRow("Total monthly EMI", (m) => money(m.total_emi))}
          {metricRow("Total EMI ÷ income", (m) => pct(m.total_emi_to_income, 0))}
          {metricRow("Total interest over the term", (m) => money(m.total_interest))}
          <tr className="border-b border-slate-200 font-semibold dark:border-slate-700">
            <th scope="row" className="py-1 pr-3 text-left">Simulated default probability</th>
            {columns.map((c) => {
              const d = c.isBase ? null : (c.ev as ScenarioResult).delta_vs_base?.default_probability_simulated;
              return (
                <td key={c.title} className="pr-3 tabular-nums">
                  {pct(c.ev.metrics.default_probability_simulated)}
                  {d !== null && d !== undefined && <span className="ml-1 text-xs font-normal">({d >= 0 ? "+" : "−"}{Math.abs(d * 100).toFixed(1)} pts model output)</span>}
                </td>
              );
            })}
          </tr>
          <tr>
            <th scope="row" className="py-1 pr-3 text-left font-normal">Demonstration policy</th>
            {columns.map((c) => (
              <td key={c.title} className="pr-3 align-top">
                <span className="font-medium">{c.ev.meets_policy ? "Meets all rules" : "Does not meet all rules"}</span>
                <ul className="text-xs text-slate-600 dark:text-slate-400">
                  {c.ev.policy.rules.map((r) => <li key={r.rule}>{r.passed ? "✓" : "✗"} {r.rule}</li>)}
                  {c.ev.feasibility_issues.map((f) => <li key={f}>✗ {f}</li>)}
                </ul>
              </td>
            ))}
          </tr>
        </tbody>
      </table>
      <p className="mt-1 text-xs text-slate-500">Compared with: {base.inputs.loan_amount ? "the base application" : ""}. Probability changes are changes in the model&apos;s output, not proven effects.</p>
    </div>
  );
}
