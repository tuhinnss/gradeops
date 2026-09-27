"use client";

import { useState } from "react";
import { HistoryTable } from "@/components/grading/HistoryTable";
import { Card, ErrorState, PageHeader, Select, SkeletonRows } from "@/components/ui";
import { ta } from "@/lib/endpoints";
import { useApi } from "@/lib/hooks";

export default function TAHistoryPage() {
  const [action, setAction] = useState("");
  const history = useApi(() => ta.history({ action: action || undefined, limit: 200 }), [action]);
  return (
    <>
      <PageHeader
        title="Review history"
        subtitle={history.data ? `${history.data.total} recorded action${history.data.total === 1 ? "" : "s"} from the review audit log.` : "From the review audit log."}
        actions={
          <Select aria-label="Filter by action" value={action} onChange={(e) => setAction(e.target.value)} className="w-44">
            <option value="">All actions</option>
            <option value="approve">Approved</option>
            <option value="override">Overridden</option>
            <option value="escalate">Escalated</option>
          </Select>
        }
      />
      {history.error && <ErrorState message={history.error} onRetry={history.reload} />}
      <Card>{history.data ? <HistoryTable items={history.data.items} reviewBasePath="/ta/reviews" /> : <SkeletonRows rows={6} className="p-4" />}</Card>
    </>
  );
}
