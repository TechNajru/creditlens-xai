import { ApplicantDashboard } from "@/components/ApplicantDashboard";
import { RequireAuth } from "@/components/RequireAuth";

export const metadata = { title: "My applications — CreditLens XAI" };

export default function Page() {
  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold">My applications</h1>
      <RequireAuth roles={["applicant"]}><ApplicantDashboard /></RequireAuth>
    </div>
  );
}
