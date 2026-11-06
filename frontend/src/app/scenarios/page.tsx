import { ScenarioWorkbench } from "@/components/ScenarioWorkbench";

export const metadata = { title: "What-if & alternatives — CreditLens XAI" };

export default function Page() {
  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold">What-if simulator and alternatives</h1>
      <ScenarioWorkbench />
    </div>
  );
}
