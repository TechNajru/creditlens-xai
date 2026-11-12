import { RequireAuth } from "@/components/RequireAuth";
import { FairnessDashboard } from "@/components/FairnessDashboard";

export const metadata = { title: "Fairness audit — CreditLens XAI" };

export default function Page() {
  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold">Fairness audit (public-data model)</h1>
      <RequireAuth roles={["reviewer", "admin"]}><FairnessDashboard /></RequireAuth>
    </div>
  );
}
