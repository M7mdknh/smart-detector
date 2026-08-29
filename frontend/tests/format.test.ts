import { describe, expect, it } from "vitest";
import { formatMinutes, formatPpm, isStale } from "../src/lib/format";

describe("formatPpm", () => {
  it("formats a whole number of ppm", () => {
    expect(formatPpm(4523.7)).toBe("4524 ppm");
  });
  it("shows -- for null/undefined", () => {
    expect(formatPpm(null)).toBe("--");
    expect(formatPpm(undefined)).toBe("--");
  });
});

describe("formatMinutes", () => {
  it("shows <1 min for sub-minute values", () => {
    expect(formatMinutes(0.4)).toBe("<1 min");
  });
  it("rounds to whole minutes", () => {
    expect(formatMinutes(34.6)).toBe("35 min");
  });
  it("shows -- for null", () => {
    expect(formatMinutes(null)).toBe("--");
  });
});

describe("isStale", () => {
  it("flags readings older than the threshold", () => {
    const now = Date.now();
    const old = new Date(now - 700_000).toISOString();
    expect(isStale(old, now, 600)).toBe(true);
  });
  it("does not flag fresh readings", () => {
    const now = Date.now();
    const fresh = new Date(now - 10_000).toISOString();
    expect(isStale(fresh, now, 600)).toBe(false);
  });
  it("treats missing timestamps as stale", () => {
    expect(isStale(null, Date.now(), 600)).toBe(true);
  });
});
