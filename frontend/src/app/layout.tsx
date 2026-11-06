import type { Metadata } from "next";
import "./globals.css";
import { NavBar } from "@/components/NavBar";

export const metadata: Metadata = {
  title: "CreditLens XAI — educational credit-risk prototype",
  description:
    "An educational, explainable and calibrated credit-risk decision-support prototype. Not a lender, not a credit score.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="h-full antialiased">
      <body className="flex min-h-full flex-col">
        <a href="#main" className="sr-only focus:not-sr-only focus:p-2">Skip to content</a>
        <NavBar />
        <main id="main" className="mx-auto w-full max-w-5xl flex-1 px-4 py-8">{children}</main>
        <footer className="border-t border-slate-200 px-4 py-4 text-center text-xs text-slate-500 dark:border-slate-800">
          CreditLens XAI is an educational prototype. It is not a bank, does not issue loans, is not a credit-bureau score
          and does not guarantee approval. Models here are trained on synthetic or public 2005 data.
        </footer>
      </body>
    </html>
  );
}
