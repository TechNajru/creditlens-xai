import { AssessmentForm } from "@/components/AssessmentForm";
import { PUBLIC_CONFIG } from "@/lib/fields";

export const metadata = { title: "Public-data model — CreditLens XAI" };

export default function Page() {
  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold">{PUBLIC_CONFIG.title}</h1>
      <AssessmentForm config={PUBLIC_CONFIG} />
    </div>
  );
}
