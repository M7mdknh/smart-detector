import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";

export function useDashboardSnapshot() {
  return useQuery({
    queryKey: ["dashboard-snapshot"],
    queryFn: api.dashboardSnapshot,
    refetchInterval: 5000,
  });
}

export function useIncidentDetail(incidentId: string | null) {
  return useQuery({
    queryKey: ["incident", incidentId],
    queryFn: () => api.getIncident(incidentId as string),
    enabled: !!incidentId,
  });
}

export function useIncidentAudit(incidentId: string | null) {
  return useQuery({
    queryKey: ["incident-audit", incidentId],
    queryFn: () => api.incidentAudit(incidentId as string),
    enabled: !!incidentId,
  });
}

export function useIncidentAction(incidentId: string | null) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { action: string; comment?: string; expected_version: number }) =>
      api.incidentAction(incidentId as string, { ...body, actor: "HUMAN" }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["incident", incidentId] });
      qc.invalidateQueries({ queryKey: ["incident-audit", incidentId] });
      qc.invalidateQueries({ queryKey: ["dashboard-snapshot"] });
      qc.invalidateQueries({ queryKey: ["incidents"] });
    },
  });
}
