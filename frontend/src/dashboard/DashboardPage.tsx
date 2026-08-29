import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Header } from "./Header";
import { StatusCards } from "./StatusCards";
import { GasChart } from "./GasChart";
import { CameraPanel } from "./CameraPanel";
import { IncidentTable } from "./IncidentTable";
import { ReviewDrawer } from "./ReviewDrawer";
import { useDashboardSnapshot } from "./hooks";
import { useLiveConnection } from "../lib/useWebSocket";
import { api } from "../api/client";

export function DashboardPage() {
  const connection = useLiveConnection();
  const { data: snapshot, isError } = useDashboardSnapshot();
  const { data: incidents } = useQuery({ queryKey: ["incidents"], queryFn: () => api.listIncidents() });
  const [reviewId, setReviewId] = useState<string | null>(null);
  const [nowMs, setNowMs] = useState(Date.now());

  useEffect(() => {
    const t = setInterval(() => setNowMs(Date.now()), 1000);
    return () => clearInterval(t);
  }, []);

  return (
    <div className="page">
      <Header snapshot={snapshot} connection={connection} />
      {isError && <div className="stale-banner">Could not reach the backend. Showing last known state.</div>}
      <main className="dashboard-main">
        <StatusCards snapshot={snapshot} nowMs={nowMs} />
        <div className="main-row">
          <GasChart snapshot={snapshot} />
          <CameraPanel vision={snapshot?.vision} nowMs={nowMs} />
        </div>
        <IncidentTable incidents={incidents} nowMs={nowMs} onReview={setReviewId} />
      </main>
      <ReviewDrawer incidentId={reviewId} onClose={() => setReviewId(null)} />
    </div>
  );
}
