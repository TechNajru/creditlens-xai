"use client";
import { Bar, BarChart, Cell, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { Contribution } from "@/lib/types";

export function ContributionChart({ items }: { items: Contribution[] }) {
  const data = items.slice(0, 10).map((c) => ({ name: c.label, value: Number(c.contribution.toFixed(4)) }));
  return (
    <div role="img" aria-label="Bar chart of the largest feature contributions to the model's raw risk score" className="h-80 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} layout="vertical" margin={{ left: 16, right: 24 }}>
          <XAxis type="number" tickFormatter={(v: number) => (v > 0 ? `+${v}` : `${v}`)} />
          <YAxis type="category" dataKey="name" width={210} tick={{ fontSize: 11 }} />
          <Tooltip formatter={(v) => [Number(v) > 0 ? `+${v} (raises score)` : `${v} (lowers score)`, "Contribution"]} />
          <ReferenceLine x={0} stroke="#64748b" />
          <Bar isAnimationActive={false} dataKey="value">
            {data.map((d) => <Cell key={d.name} fill={d.value > 0 ? "#dc2626" : "#16a34a"} />)}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
