"use client";
import { Bar, CartesianGrid, ComposedChart, Legend, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { MonthRow } from "@/lib/types";

const sum = (...v: (number | null)[]) => v.reduce<number>((a, b) => a + (b ?? 0), 0);

export function MonthlyChart({ monthly }: { monthly: MonthRow[] }) {
  const data = monthly.map((m) => ({
    month: m.role === "edge_partial_possible" ? `${m.month} *` : m.month,
    Inflows: m.has_data ? sum(m.income_confirmed, m.income_likely, m.inflow_unverified, m.refunds) : null,
    Outflows: m.has_data ? sum(m.outflow_essential, m.outflow_debt, m.outflow_discretionary, m.outflow_other) : null,
    Net: m.has_data ? m.net_cashflow : null,
  }));
  return (
    <figure>
    <div role="img" aria-label="Monthly inflows, outflows and net cash flow" className="h-72 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart data={data}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis dataKey="month" />
          <YAxis />
          <Tooltip />
          <Legend />
          <Bar isAnimationActive={false} dataKey="Inflows" fill="#0284c7" />
          <Bar isAnimationActive={false} dataKey="Outflows" fill="#f59e0b" />
          <Line isAnimationActive={false} type="monotone" dataKey="Net" stroke="#111827" strokeWidth={2} />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
    <figcaption className="mt-1 text-xs text-slate-500">* First and last months may be partial; they appear here but are not used in the metrics below.</figcaption>
    </figure>
  );
}
