import type { Severity } from "../api/types";

export const SEVERITY_COLOR: Record<Severity, string> = {
  LOW: "#5b7fa6",
  MEDIUM: "#c98a1d",
  HIGH: "#d9622b",
  CRITICAL: "#c62828",
};

export const SEVERITY_ORDER: Record<Severity, number> = { CRITICAL: 4, HIGH: 3, MEDIUM: 2, LOW: 1 };

export function formatPpm(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "--";
  return `${Math.round(value)} ppm`;
}

export function formatMinutes(value: number | null | undefined): string {
  if (value === null || value === undefined) return "--";
  if (value < 1) return "<1 min";
  return `${Math.round(value)} min`;
}

export function formatAge(iso: string | null | undefined, nowMs: number): string {
  if (!iso) return "--";
  const ageSec = (nowMs - new Date(iso).getTime()) / 1000;
  if (ageSec < 0) return "0s";
  if (ageSec < 60) return `${Math.round(ageSec)}s`;
  if (ageSec < 3600) return `${Math.round(ageSec / 60)}m`;
  return `${Math.round(ageSec / 3600)}h`;
}

export function formatClock(iso: string | null | undefined): string {
  if (!iso) return "--";
  const d = new Date(iso);
  return d.toLocaleString(undefined, { hour: "2-digit", minute: "2-digit", second: "2-digit", month: "short", day: "numeric" });
}

export function isStale(iso: string | null | undefined, nowMs: number, thresholdSec: number): boolean {
  if (!iso) return true;
  return (nowMs - new Date(iso).getTime()) / 1000 > thresholdSec;
}
