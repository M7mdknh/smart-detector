import type { ReactElement } from "react";
import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { CameraPanel } from "../src/dashboard/CameraPanel";
import type { VisionStatus } from "../src/api/types";
import { api } from "../src/api/client";

vi.spyOn(api, "visionZones").mockResolvedValue({
  version: "1.0",
  camera_id: "camera-1",
  zones: [{ id: "zone-1", type: "GAS_EXPOSURE", label: "Gas zone", points: [[0, 0], [1, 0], [1, 1], [0, 1]] }],
});

function withClient(ui: ReactElement) {
  const client = new QueryClient();
  return <QueryClientProvider client={client}>{ui}</QueryClientProvider>;
}

function baseVision(overrides: Partial<VisionStatus> = {}): VisionStatus {
  return {
    camera_id: "camera-1",
    status: "OK",
    model_version: "ppe-yolo11n-1.1",
    last_frame_age_seconds: 1,
    fps: 8,
    tracks: [],
    ...overrides,
  };
}

describe("CameraPanel", () => {
  it("renders a live annotated frame image pointed at the frame.jpg endpoint when not degraded", () => {
    render(withClient(<CameraPanel vision={baseVision()} nowMs={1000} />));
    const img = screen.getByAltText(/Live annotated camera\/replay frame/i) as HTMLImageElement;
    expect(img).toBeInTheDocument();
    expect(img.src).toContain("/vision/frame.jpg?t=1000");
  });

  it("does not render an annotated frame image when the camera/detector is degraded", () => {
    render(withClient(<CameraPanel vision={baseVision({ status: "UNAVAILABLE" })} nowMs={1000} />));
    expect(screen.queryByAltText(/Live annotated camera\/replay frame/i)).not.toBeInTheDocument();
    expect(screen.getByText(/Camera\/model unavailable/)).toBeInTheDocument();
  });

  it("shows a loading skeleton when vision status has not arrived yet", () => {
    render(withClient(<CameraPanel vision={undefined} nowMs={1000} />));
    expect(screen.getByText(/Loading camera/)).toBeInTheDocument();
  });

  it("still shows the structured detection list alongside the annotated frame", () => {
    const vision = baseVision({
      tracks: [
        {
          evidence_id: "ev-1", track_id: 3, detected_class: "person", confidence: 0.9,
          bbox: [0.1, 0.1, 0.3, 0.9], helmet_state: "COMPLIANT", vest_state: "UNKNOWN",
          gas_zone_membership: "OUTSIDE", overhead_zone_membership: "OUTSIDE",
          event_time: new Date().toISOString(),
        },
      ],
    });
    render(withClient(<CameraPanel vision={vision} nowMs={1000} />));
    expect(screen.getByText("Worker #3")).toBeInTheDocument();
    expect(screen.getByAltText(/Live annotated camera\/replay frame/i)).toBeInTheDocument();
  });
});
