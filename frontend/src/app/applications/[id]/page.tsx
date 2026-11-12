"use client";
import { useParams } from "next/navigation";
import { ApplicationWorkflow } from "@/components/ApplicationWorkflow";
import { RequireAuth } from "@/components/RequireAuth";

export default function Page() {
  const params = useParams<{ id: string }>();
  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold">Application</h1>
      <RequireAuth roles={["applicant"]}><ApplicationWorkflow id={params.id} /></RequireAuth>
    </div>
  );
}
