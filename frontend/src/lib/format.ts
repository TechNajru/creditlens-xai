export const pct = (p: number, digits = 1) => `${(p * 100).toFixed(digits)}%`;
export const signed = (n: number, digits = 3) => `${n >= 0 ? "+" : "−"}${Math.abs(n).toFixed(digits)}`;
export const money = (n: number | null | undefined, currency = "") =>
  n === null || n === undefined ? "unknown" : `${currency}${Math.round(n).toLocaleString("en-IN")}`;
export const titleCase = (s: string) => s.replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase());
