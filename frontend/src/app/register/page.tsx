import { RegisterForm } from "@/components/RegisterForm";

export const metadata = { title: "Register — CreditLens XAI" };

export default function Page() {
  return (
    <div className="space-y-4">
      <h1 className="text-center text-2xl font-bold">Create an applicant account</h1>
      <RegisterForm />
    </div>
  );
}
