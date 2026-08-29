import type { ReactElement } from "react";
import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ReviewDrawer } from "../src/dashboard/ReviewDrawer";
import { api, ApiError } from "../src/api/client";
import type { Incident } from "../src/api/types";

function baseIncident(overrides: Partial<Incident> = {}): Incident {
  return {
    incident_id: "inc-1", type: "PPE_HELMET_OVERHEAD_VIOLATION", zone_id: "zone-1", gas: null,
    severity: "HIGH", confidence: null, state: "OPEN", opened_at: new Date().toISOString(),
    updated_at: new Date().toISOString(), acknowledged_at: null, resolved_at: null,
    dedup_key: "zone-1:PPE_HELMET_OVERHEAD_VIOLATION", reason_codes: ["PPE_HELMET_OVERHEAD_VIOLATION"],
    explanation: "Missing helmet compliance persisted while a worker was in the overhead-work zone.",
    recommended_action: "Investigate", version: 3, allowed_actions: ["ACKNOWLEDGE"],
    ...overrides,
  };
}

function withClient(ui: ReactElement) {
  const client = new QueryClient();
  return <QueryClientProvider client={client}>{ui}</QueryClientProvider>;
}

beforeEach(() => {
  vi.restoreAllMocks();
  vi.spyOn(api, "incidentAudit").mockResolvedValue([]);
});

describe("ReviewDrawer version-conflict auto-retry", () => {
  it("transparently retries once with the freshly re-fetched version on VERSION_CONFLICT, instead of surfacing an error", async () => {
    const stale = baseIncident({ version: 3 });
    const fresh = baseIncident({ version: 4 });

    vi.spyOn(api, "getIncident")
      .mockResolvedValueOnce(stale) // initial drawer load
      .mockResolvedValueOnce(fresh); // re-fetch triggered by the conflict retry

    const action = vi
      .spyOn(api, "incidentAction")
      .mockImplementationOnce(() => Promise.reject(new ApiError("VERSION_CONFLICT", "stale version", 409, {})))
      .mockImplementationOnce(() => Promise.resolve({ ...fresh, state: "ACKNOWLEDGED", version: 5 }));

    render(withClient(<ReviewDrawer incidentId="inc-1" onClose={() => {}} />));

    const ackButton = await screen.findByRole("button", { name: "Acknowledge" });
    await userEvent.click(ackButton);

    await waitFor(() => expect(action).toHaveBeenCalledTimes(2));
    expect(action.mock.calls[0][1].expected_version).toBe(3);
    expect(action.mock.calls[1][1].expected_version).toBe(4);

    // No conflict banner: the retry succeeded transparently.
    expect(screen.queryByText(/changed since you loaded it/)).not.toBeInTheDocument();
    expect(screen.queryByText(/changed again since the retry/)).not.toBeInTheDocument();
  });

  it("retries up to the bounded limit under sustained conflicts, then surfaces a message instead of retrying forever", async () => {
    const stale = baseIncident({ version: 3 });

    vi.spyOn(api, "getIncident").mockResolvedValue(stale);

    const action = vi.spyOn(api, "incidentAction").mockImplementation(() =>
      Promise.reject(new ApiError("VERSION_CONFLICT", "stale version", 409, {})),
    );

    render(withClient(<ReviewDrawer incidentId="inc-1" onClose={() => {}} />));

    const ackButton = await screen.findByRole("button", { name: "Acknowledge" });
    await userEvent.click(ackButton);

    await screen.findByText(/keeps changing faster than the retry could keep up/);
    // 1 initial attempt + 3 bounded retries = 4 total calls, never unbounded.
    expect(action).toHaveBeenCalledTimes(4);
  });
});
