import { ApplicationWorkflow } from "@/components/ApplicationWorkflow";
import { RequireAuth } from "@/components/RequireAuth";

export const metadata = { title: "New application — CreditLens XAI" };

export default function Page() {
  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold">New application</h1>
      <RequireAuth roles={["applicant"]}><ApplicationWorkflow /></RequireAuth>
    </div>
  );
}
