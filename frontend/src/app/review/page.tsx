import { RequireAuth } from "@/components/RequireAuth";
import { ReviewQueue } from "@/components/ReviewQueue";

export const metadata = { title: "Review queue — CreditLens XAI" };

export default function Page() {
  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold">Review queue</h1>
      <RequireAuth roles={["reviewer"]}><ReviewQueue /></RequireAuth>
    </div>
  );
}
