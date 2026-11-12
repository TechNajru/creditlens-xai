import { LoginForm } from "@/components/LoginForm";

export const metadata = { title: "Log in — CreditLens XAI" };

export default function Page() {
  return (
    <div className="space-y-4">
      <h1 className="text-center text-2xl font-bold">Log in</h1>
      <LoginForm />
    </div>
  );
}
