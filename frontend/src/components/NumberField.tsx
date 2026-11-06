interface Props {
  id: string; label: string; value: string; onChange: (v: string) => void;
  hint?: string; error?: string; disabled?: boolean;
}

export function NumberField({ id, label, value, onChange, hint, error, disabled }: Props) {
  const describedBy = [hint ? `${id}-hint` : "", error ? `${id}-error` : ""].filter(Boolean).join(" ") || undefined;
  return (
    <div>
      <label htmlFor={id} className="block text-sm font-medium">{label}</label>
      <input
        id={id} name={id} type="text" inputMode="decimal" autoComplete="off"
        value={value} disabled={disabled} onChange={(e) => onChange(e.target.value)}
        aria-invalid={error ? true : undefined} aria-describedby={describedBy}
        className={`mt-1 w-full rounded-md border px-3 py-2 text-sm bg-white dark:bg-slate-900 focus:outline-none focus:ring-2 focus:ring-sky-500 disabled:opacity-50 ${error ? "border-red-500" : "border-slate-300 dark:border-slate-700"}`}
      />
      {hint && <p id={`${id}-hint`} className="mt-1 text-xs text-slate-500 dark:text-slate-400">{hint}</p>}
      {error && <p id={`${id}-error`} className="mt-1 text-xs font-medium text-red-700 dark:text-red-300">{error}</p>}
    </div>
  );
}
