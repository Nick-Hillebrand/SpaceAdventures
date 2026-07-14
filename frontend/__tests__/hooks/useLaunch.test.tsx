import { renderHook, waitFor } from "@testing-library/react";
import { QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import { describe, it, expect } from "vitest";
import type { ReactNode } from "react";
import { useLaunch } from "@/hooks/useLaunch";
import { makeQueryClient } from "@/testUtils";
import { server } from "@/msw/server";
import i18n from "@/i18n";

function wrapper({ children }: { children: ReactNode }) {
  const client = makeQueryClient();
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

describe("useLaunch", () => {
  it("fetches the launch for the given id", async () => {
    server.use(
      http.get("/api/v1/launches/l-1", () =>
        HttpResponse.json({ ll2_id: "l-1", name: "Falcon 9 | Starlink" }),
      ),
    );

    const { result } = renderHook(() => useLaunch("l-1"), { wrapper });

    await waitFor(() => expect(result.current.data).toBeDefined());
    expect(result.current.data?.ll2_id).toBe("l-1");
  });

  it("queries with the current resolved language", async () => {
    let capturedUrl = "";
    server.use(
      http.get("/api/v1/launches/l-1", ({ request }) => {
        capturedUrl = request.url;
        return HttpResponse.json({ ll2_id: "l-1", name: "Falcon 9 | Starlink" });
      }),
    );

    renderHook(() => useLaunch("l-1"), { wrapper });

    await waitFor(() => expect(capturedUrl).toContain("lang=en"));
  });

  it("does not fetch when id is undefined", async () => {
    let called = false;
    server.use(
      http.get("/api/v1/launches/:id", () => {
        called = true;
        return HttpResponse.json({ ll2_id: "l-1", name: "Falcon 9 | Starlink" });
      }),
    );

    const { result } = renderHook(() => useLaunch(undefined), { wrapper });

    expect(result.current.fetchStatus).toBe("idle");
    expect(called).toBe(false);
  });

  it("surfaces an error when the request fails", async () => {
    server.use(
      http.get("/api/v1/launches/does-not-exist", () =>
        HttpResponse.json({ detail: "Launch not found" }, { status: 404 }),
      ),
    );

    const { result } = renderHook(() => useLaunch("does-not-exist"), { wrapper });

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(result.current.data).toBeUndefined();
  });

  it("falls back to English when i18n has no resolved language yet", async () => {
    let capturedUrl = "";
    server.use(
      http.get("/api/v1/launches/l-1", ({ request }) => {
        capturedUrl = request.url;
        return HttpResponse.json({ ll2_id: "l-1", name: "Falcon 9 | Starlink" });
      }),
    );
    const original = i18n.resolvedLanguage;
    i18n.resolvedLanguage = undefined;

    try {
      renderHook(() => useLaunch("l-1"), { wrapper });
      await waitFor(() => expect(capturedUrl).toContain("lang=en"));
    } finally {
      i18n.resolvedLanguage = original;
    }
  });
});
