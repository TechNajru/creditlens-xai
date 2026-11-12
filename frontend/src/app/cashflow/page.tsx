import { RequireAuth } from "@/components/RequireAuth";
import { CashflowWorkbench } from "@/components/CashflowWorkbench";

export const metadata = { title: "Cash-flow upload — CreditLens XAI" };

export default function Page() {
  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold">Cash-flow upload and summary</h1>
      <RequireAuth><CashflowWorkbench /></RequireAuth>
    </div>
  );
}
