import { renderHook, waitFor } from "@testing-library/react";
import { QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import { describe, it, expect } from "vitest";
import type { ReactNode } from "react";
import { useLaunchHistory } from "@/hooks/useLaunchHistory";
import { makeQueryClient } from "@/testUtils";
import { server } from "@/msw/server";

function wrapper({ children }: { children: ReactNode }) {
  const client = makeQueryClient();
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

describe("useLaunchHistory", () => {
  it("fetches history for the given launch id", async () => {
    server.use(
      http.get("/api/v1/launches/l-1/history", () =>
        HttpResponse.json({
          data: [
            {
              change_type: "net",
              old_value: "2099-01-01T00:00:00+00:00",
              new_value: "2099-01-02T00:00:00+00:00",
              detected_at: "2099-01-01T00:05:00+00:00",
            },
          ],
        }),
      ),
    );

    const { result } = renderHook(() => useLaunchHistory("l-1"), { wrapper });

    await waitFor(() => expect(result.current.data).toBeDefined());
    expect(result.current.data?.data).toHaveLength(1);
    expect(result.current.data?.data[0].change_type).toBe("net");
  });

  it("does not fetch when id is undefined", async () => {
    let called = false;
    server.use(
      http.get("/api/v1/launches/:id/history", () => {
        called = true;
        return HttpResponse.json({ data: [] });
      }),
    );

    const { result } = renderHook(() => useLaunchHistory(undefined), { wrapper });

    expect(result.current.fetchStatus).toBe("idle");
    expect(called).toBe(false);
  });

  it("surfaces an error when the request fails", async () => {
    server.use(
      http.get("/api/v1/launches/l-err/history", () =>
        HttpResponse.json({ error: { code: "NOT_FOUND", message: "nope" } }, { status: 404 }),
      ),
    );

    const { result } = renderHook(() => useLaunchHistory("l-err"), { wrapper });

    await waitFor(() => expect(result.current.isError).toBe(true));
  });
});
