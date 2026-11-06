import type { ReactNode } from "react";

type Tone = "error" | "warning" | "info" | "success";
const TONES: Record<Tone, string> = {
  error: "border-red-300 bg-red-50 text-red-900 dark:border-red-800 dark:bg-red-950 dark:text-red-100",
  warning: "border-amber-300 bg-amber-50 text-amber-900 dark:border-amber-700 dark:bg-amber-950 dark:text-amber-100",
  info: "border-sky-300 bg-sky-50 text-sky-900 dark:border-sky-800 dark:bg-sky-950 dark:text-sky-100",
  success: "border-emerald-300 bg-emerald-50 text-emerald-900 dark:border-emerald-800 dark:bg-emerald-950 dark:text-emerald-100",
};
const LABEL: Record<Tone, string> = { error: "Error", warning: "Warning", info: "Note", success: "Done" };

export function Notice({ tone = "info", title, children }: { tone?: Tone; title?: string; children: ReactNode }) {
  return (
    <div role={tone === "error" ? "alert" : "status"} className={`rounded-lg border p-3 text-sm ${TONES[tone]}`}>
      <p className="font-semibold">{title ?? LABEL[tone]}</p>
      <div className="mt-1">{children}</div>
    </div>
  );
}

export function Spinner({ label }: { label: string }) {
  return (
    <p role="status" aria-live="polite" className="flex items-center gap-2 text-sm text-slate-600 dark:text-slate-300">
      <span className="inline-block h-4 w-4 animate-spin rounded-full border-2 border-slate-400 border-t-transparent" aria-hidden="true" />
      {label}
    </p>
  );
}
