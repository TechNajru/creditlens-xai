import type { AppStatus } from "@/lib/types";

const LABEL: Record<AppStatus, string> = {
  draft: "Draft", submitted: "Submitted", validation: "Validating", assessed: "Assessed",
  manual_review: "In human review", info_requested: "Information requested", final_demo_decision: "Demo decision recorded",
};
const TONE: Record<AppStatus, string> = {
  draft: "bg-slate-200 text-slate-900", submitted: "bg-sky-200 text-sky-950", validation: "bg-sky-200 text-sky-950",
  assessed: "bg-sky-200 text-sky-950", manual_review: "bg-amber-200 text-amber-950",
  info_requested: "bg-orange-200 text-orange-950", final_demo_decision: "bg-emerald-200 text-emerald-950",
};

export function StatusBadge({ status }: { status: AppStatus }) {
  return <span className={`inline-block rounded-full px-2.5 py-0.5 text-xs font-semibold ${TONE[status]}`}>{LABEL[status]}</span>;
}
export const statusLabel = (s: AppStatus) => LABEL[s];
