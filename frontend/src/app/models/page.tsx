import { EvaluationDashboard } from "@/components/EvaluationDashboard";

export const metadata = { title: "Model evaluation — CreditLens XAI" };

export default function Page() {
  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold">Model evaluation</h1>
      <EvaluationDashboard />
    </div>
  );
}
