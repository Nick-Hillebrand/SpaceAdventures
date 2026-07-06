import { renderHook, waitFor } from "@testing-library/react";
import { QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import { describe, it, expect } from "vitest";
import type { ReactNode } from "react";
import { useLaunches } from "@/hooks/useLaunches";
import { makeQueryClient } from "@/testUtils";
import { server } from "@/msw/server";
import i18n from "@/i18n";

function wrapper({ children }: { children: ReactNode }) {
  const client = makeQueryClient();
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

describe("useLaunches", () => {
  it("queries with the current resolved language", async () => {
    let capturedUrl = "";
    server.use(
      http.get("/api/v1/launches/upcoming", ({ request }) => {
        capturedUrl = request.url;
        return HttpResponse.json({ launches: [] });
      }),
    );

    renderHook(() => useLaunches(), { wrapper });

    await waitFor(() => expect(capturedUrl).toContain("lang=en"));
  });

  it("falls back to English when i18n has no resolved language yet", async () => {
    let capturedUrl = "";
    server.use(
      http.get("/api/v1/launches/upcoming", ({ request }) => {
        capturedUrl = request.url;
        return HttpResponse.json({ launches: [] });
      }),
    );
    const original = i18n.resolvedLanguage;
    i18n.resolvedLanguage = undefined;

    try {
      renderHook(() => useLaunches(), { wrapper });
      await waitFor(() => expect(capturedUrl).toContain("lang=en"));
    } finally {
      i18n.resolvedLanguage = original;
    }
  });
});
