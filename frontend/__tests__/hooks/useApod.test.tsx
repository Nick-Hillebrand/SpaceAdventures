import { renderHook, waitFor } from "@testing-library/react";
import { QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import { describe, it, expect } from "vitest";
import type { ReactNode } from "react";
import { useApod } from "@/hooks/useApod";
import { makeQueryClient } from "@/testUtils";
import { server } from "@/msw/server";
import i18n from "@/i18n";

function wrapper({ children }: { children: ReactNode }) {
  const client = makeQueryClient();
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

describe("useApod", () => {
  it("queries with the current language and omits the date param when none is given", async () => {
    let capturedUrl = "";
    server.use(
      http.get("/api/v1/apod", ({ request }) => {
        capturedUrl = request.url;
        return HttpResponse.json({});
      }),
    );

    renderHook(() => useApod(), { wrapper });

    await waitFor(() => expect(capturedUrl).toContain("lang=en"));
    expect(capturedUrl).not.toContain("date=");
  });

  it("includes the date param when a date is provided", async () => {
    let capturedUrl = "";
    server.use(
      http.get("/api/v1/apod", ({ request }) => {
        capturedUrl = request.url;
        return HttpResponse.json({});
      }),
    );

    renderHook(() => useApod("2024-01-01"), { wrapper });

    await waitFor(() => expect(capturedUrl).toContain("date=2024-01-01"));
  });

  it("falls back to English when i18n has no resolved language yet", async () => {
    let capturedUrl = "";
    server.use(
      http.get("/api/v1/apod", ({ request }) => {
        capturedUrl = request.url;
        return HttpResponse.json({});
      }),
    );
    const original = i18n.resolvedLanguage;
    i18n.resolvedLanguage = undefined;

    try {
      renderHook(() => useApod(), { wrapper });
      await waitFor(() => expect(capturedUrl).toContain("lang=en"));
    } finally {
      i18n.resolvedLanguage = original;
    }
  });
});
