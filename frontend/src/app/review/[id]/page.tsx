"use client";
import { useParams } from "next/navigation";
import { RequireAuth } from "@/components/RequireAuth";
import { ReviewDetail } from "@/components/ReviewDetail";

export default function Page() {
  const params = useParams<{ id: string }>();
  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold">Review application</h1>
      <RequireAuth roles={["reviewer"]}><ReviewDetail id={params.id} /></RequireAuth>
    </div>
  );
}
