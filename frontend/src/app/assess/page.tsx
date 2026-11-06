import { AssessmentForm } from "@/components/AssessmentForm";
import { LOAN_CONFIG } from "@/lib/fields";

export const metadata = { title: "Loan simulation — CreditLens XAI" };

export default function Page() {
  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold">{LOAN_CONFIG.title}</h1>
      <AssessmentForm config={LOAN_CONFIG} />
    </div>
  );
}
