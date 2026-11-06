"use client";
import { useState } from "react";
import { ApiError, postJson } from "@/lib/api";
import { type AssessmentConfig, validateFields } from "@/lib/fields";
import type { PredictionResponse } from "@/lib/types";
import { NumberField } from "./NumberField";
import { Notice, Spinner } from "./Notice";
import { PredictionResult } from "./PredictionResult";

export function AssessmentForm({ config }: { config: AssessmentConfig }) {
  const [values, setValues] = useState<Record<string, string>>({});
  const [unknown, setUnknown] = useState<Record<string, boolean>>({});
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(false);
  const [apiError, setApiError] = useState<string | null>(null);
  const [result, setResult] = useState<PredictionResponse | null>(null);

  const groups = Array.from(new Set(config.fields.map((f) => f.group ?? "")));

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setApiError(null);
    const v = validateFields(config.fields, values, unknown);
    setErrors(v.errors);
    if (!v.ok) { setResult(null); return; }
    setLoading(true);
    try {
      setResult(await postJson<PredictionResponse>(config.endpoint, v.payload));
    } catch (err) {
      setResult(null);
      setApiError(err instanceof ApiError ? err.message : "Something went wrong. Please try again.");
    } finally {
      setLoading(false);
    }
  }

  function fill(example: Record<string, string>) {
    setValues(example);
    setUnknown(Object.fromEntries(config.fields.filter((f) => f.optional).map((f) => [f.name, (example[f.name] ?? "") === ""])));
    setErrors({}); setResult(null); setApiError(null);
  }

  return (
    <div className="space-y-6">
      <Notice tone="info" title="Prototype notice">{config.introNote}</Notice>
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-sm text-slate-600 dark:text-slate-300">Fictional examples (demo fixtures, not real people):</span>
        {config.examples.map((ex) => (
          <button key={ex.label} type="button" onClick={() => fill(ex.values)}
            className="rounded-md border border-slate-300 px-3 py-1 text-sm hover:bg-slate-100 focus:outline-none focus:ring-2 focus:ring-sky-500 dark:border-slate-600 dark:hover:bg-slate-800">
            {ex.label}
          </button>
        ))}
      </div>
      <form onSubmit={onSubmit} noValidate aria-busy={loading} className="space-y-6">
        {groups.map((g) => (
          <fieldset key={g || "main"} className="rounded-lg border border-slate-200 p-4 dark:border-slate-700">
            {g && <legend className="px-1 text-sm font-semibold">{g}</legend>}
            <div className="grid gap-4 md:grid-cols-2">
              {config.fields.filter((f) => (f.group ?? "") === g).map((f) => (
                <div key={f.name}>
                  <NumberField id={`${config.key}-${f.name}`} label={f.label} hint={f.hint}
                    value={values[f.name] ?? ""} error={errors[f.name]}
                    disabled={f.optional && unknown[f.name]}
                    onChange={(val) => setValues((s) => ({ ...s, [f.name]: val }))} />
                  {f.optional && (
                    <label className="mt-1 flex items-center gap-2 text-sm">
                      <input type="checkbox" checked={!!unknown[f.name]}
                        onChange={(e) => setUnknown((s) => ({ ...s, [f.name]: e.target.checked }))} />
                      Unknown / not available
                    </label>
                  )}
                </div>
              ))}
            </div>
          </fieldset>
        ))}
        {Object.keys(errors).length > 0 && (
          <Notice tone="error" title="Please fix the highlighted fields">{Object.keys(errors).length} field(s) need attention.</Notice>
        )}
        <button type="submit" disabled={loading}
          className="rounded-md bg-sky-700 px-5 py-2 font-medium text-white hover:bg-sky-800 focus:outline-none focus:ring-2 focus:ring-sky-500 focus:ring-offset-2 disabled:opacity-60">
          {loading ? "Assessing…" : "Run assessment"}
        </button>
      </form>
      {loading && <Spinner label="Running the model and computing the explanation…" />}
      {apiError && <Notice tone="error" title="The assessment could not be completed">{apiError}</Notice>}
      {result && <PredictionResult result={result} />}
      {!result && !loading && !apiError && (
        <p className="text-sm text-slate-600 dark:text-slate-400">No result yet. Fill in the form (or load a fictional example) and run the assessment.</p>
      )}
    </div>
  );
}
