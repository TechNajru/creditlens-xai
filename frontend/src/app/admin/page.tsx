import { AdminConsole } from "@/components/AdminConsole";
import { RequireAuth } from "@/components/RequireAuth";

export const metadata = { title: "Admin — CreditLens XAI" };

export default function Page() {
  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold">Administration</h1>
      <RequireAuth roles={["admin"]}><AdminConsole /></RequireAuth>
    </div>
  );
}
