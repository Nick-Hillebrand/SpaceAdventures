import { renderHook, waitFor } from "@testing-library/react";
import { QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import { describe, it, expect } from "vitest";
import type { ReactNode } from "react";
import { useEphemerides, useTrackedSpacecraftEphemerides } from "@/hooks/useEphemerides";
import { TRACKED_SPACECRAFT } from "@/solar/spacecraft";
import { makeQueryClient } from "@/testUtils";
import { server } from "@/msw/server";

function wrapper({ children }: { children: ReactNode }) {
  const client = makeQueryClient();
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

const JWST_RESPONSE = {
  slug: "jwst",
  name_key: "spacecraft.jwst",
  points: [
    { t: "2026-01-01T00:00:00Z", x: 1, y: 0, z: 0 },
    { t: "2026-01-02T00:00:00Z", x: 1.1, y: 0, z: 0 },
  ],
};

describe("useEphemerides", () => {
  it("fetches the ephemeris series for the given slug, requesting a from/to window", async () => {
    let capturedUrl: URL | null = null;
    server.use(
      http.get("/api/v1/ephemerides/jwst", ({ request }) => {
        capturedUrl = new URL(request.url);
        return HttpResponse.json(JWST_RESPONSE);
      }),
    );

    const { result } = renderHook(() => useEphemerides("jwst"), { wrapper });

    await waitFor(() => expect(result.current.data).toBeDefined());
    expect(result.current.data?.slug).toBe("jwst");
    expect(result.current.data?.points).toHaveLength(2);
    expect(capturedUrl!.searchParams.get("from")).toBeTruthy();
    expect(capturedUrl!.searchParams.get("to")).toBeTruthy();
  });

  it("does not fetch when slug is undefined", () => {
    const { result } = renderHook(() => useEphemerides(undefined), { wrapper });
    expect(result.current.fetchStatus).toBe("idle");
  });

  it("surfaces an error when the request fails", async () => {
    server.use(
      http.get("/api/v1/ephemerides/unknown-slug", () =>
        HttpResponse.json({ error: { code: "UNKNOWN_OBJECT", message: "nope" } }, { status: 404 }),
      ),
    );

    const { result } = renderHook(() => useEphemerides("unknown-slug"), { wrapper });
    await waitFor(() => expect(result.current.isError).toBe(true));
  });
});

describe("useTrackedSpacecraftEphemerides", () => {
  it("fires one query per catalog entry and reports slug/nameKey alongside each query result", async () => {
    server.use(
      http.get("/api/v1/ephemerides/:slug", ({ params }) =>
        HttpResponse.json({ slug: params.slug, name_key: `spacecraft.${params.slug}`, points: [] }),
      ),
    );

    const { result } = renderHook(() => useTrackedSpacecraftEphemerides(), { wrapper });

    expect(result.current).toHaveLength(TRACKED_SPACECRAFT.length);
    expect(result.current.map((r) => r.slug)).toEqual(TRACKED_SPACECRAFT.map((c) => c.slug));

    await waitFor(() => expect(result.current.every((r) => r.query.data)).toBe(true));
    for (const entry of result.current) {
      expect(entry.query.data?.slug).toBe(entry.slug);
    }
  });

  it("keeps other entries usable when one catalog entry's fetch fails", async () => {
    server.use(
      http.get("/api/v1/ephemerides/:slug", ({ params }) => {
        if (params.slug === "voyager-1") {
          return HttpResponse.json({ error: { code: "UNKNOWN_OBJECT", message: "nope" } }, { status: 404 });
        }
        return HttpResponse.json({ slug: params.slug, name_key: `spacecraft.${params.slug}`, points: [] });
      }),
    );

    const { result } = renderHook(() => useTrackedSpacecraftEphemerides(), { wrapper });

    await waitFor(() => {
      const voyager = result.current.find((r) => r.slug === "voyager-1")!;
      expect(voyager.query.isError).toBe(true);
    });
    const others = result.current.filter((r) => r.slug !== "voyager-1");
    await waitFor(() => expect(others.every((r) => r.query.data)).toBe(true));
  });
});
