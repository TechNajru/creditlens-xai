import Link from "next/link";

const CARDS = [
  { href: "/assess", title: "Loan simulation", text: "Enter a loan application and see a calibrated simulated risk estimate with an explanation. Trained on synthetic data." },
  { href: "/assess-public", title: "Public-data model", text: "A separate model trained on the public UCI credit-card dataset (Taiwan, 2005)." },
  { href: "/scenarios", title: "What-if & alternatives", text: "Change loan amount or tenure, compare scenarios, and search for alternatives that meet a demonstration policy. Simulation only." },
  { href: "/cashflow", title: "Cash-flow upload", text: "Upload a transaction CSV, correct guessed categories and view a cash-flow summary. Descriptive only." },
  { href: "/models", title: "Model evaluation", text: "Calibration, threshold trade-offs, validation comparison, global SHAP importance and limited-information experiments." },
  { href: "/fairness", title: "Fairness audit", text: "Group outcomes with uncertainty, small-group warnings and one mitigation experiment (not deployed)." },
];

export default function Home() {
  return (
    <div className="space-y-10">
      <section className="space-y-3">
        <h1 className="text-3xl font-bold">CreditLens XAI</h1>
        <p className="text-lg text-slate-700 dark:text-slate-300">
          A calibrated, explainable and fairness-aware credit-risk decision-support <strong>prototype</strong> built for learning and demonstration.
        </p>
      </section>
      <section aria-labelledby="not-h" className="rounded-xl border border-amber-300 bg-amber-50 p-5 text-amber-950 dark:border-amber-700 dark:bg-amber-950 dark:text-amber-100">
        <h2 id="not-h" className="font-semibold">What this is not</h2>
        <ul className="mt-2 list-disc space-y-1 pl-5 text-sm">
          <li>Not a bank or lender; it issues no loans and guarantees no approval.</li>
          <li>Not a credit-bureau score and not validated for real lending decisions.</li>
          <li>The loan model is trained on synthetic data and says nothing about real borrowers.</li>
          <li>The public-data model reflects 2005 Taiwan credit-card clients only.</li>
          <li>Explanations describe how a model uses its inputs. They do not show causes.</li>
        </ul>
      </section>
      <section aria-labelledby="try-h">
        <h2 id="try-h" className="mb-3 text-xl font-semibold">Try it</h2>
        <div className="grid gap-4 md:grid-cols-2">
          {CARDS.map((c) => (
            <Link key={c.href} href={c.href} className="rounded-xl border border-slate-200 p-4 hover:bg-slate-50 dark:border-slate-700 dark:hover:bg-slate-900">
              <h3 className="font-semibold">{c.title}</h3>
              <p className="mt-1 text-sm text-slate-600 dark:text-slate-300">{c.text}</p>
            </Link>
          ))}
        </div>
      </section>
      <section aria-labelledby="status-h" className="text-sm text-slate-600 dark:text-slate-300">
        <h2 id="status-h" className="mb-1 text-base font-semibold text-inherit">Status</h2>
        <p>Implemented: shared feature engineering, calibration, SHAP explanations, CSV cash-flow analysis, evaluation dashboard,
          what-if and counterfactuals, fairness audit, limited-information experiments. Not built yet: accounts and roles, reviewer workflow, audit trail.</p>
      </section>
    </div>
  );
}
