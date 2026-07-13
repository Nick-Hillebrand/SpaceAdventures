import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { http, HttpResponse } from "msw";
import { server } from "@/msw/server";
import { apiGet, apiDelete, apiPost, getAccessToken, setAccessToken } from "@/lib/api";

describe("api helpers", () => {
  beforeEach(() => {
    localStorage.clear();
    setAccessToken(null);
  });

  afterEach(() => {
    localStorage.clear();
    setAccessToken(null);
  });

  it("stores and reads the access token in memory only", () => {
    setAccessToken("abc");
    expect(getAccessToken()).toBe("abc");
    setAccessToken(null);
    expect(getAccessToken()).toBeNull();
  });

  it("purges legacy localStorage token keys on module load", async () => {
    localStorage.setItem("space-adventures-access-token", "old");
    localStorage.setItem("space-adventures-refresh-token", "old-refresh");
    vi.resetModules();
    await import("@/lib/api");
    expect(localStorage.getItem("space-adventures-access-token")).toBeNull();
    expect(localStorage.getItem("space-adventures-refresh-token")).toBeNull();
  });

  it("never writes auth tokens to localStorage", async () => {
    const setItemSpy = vi.spyOn(Storage.prototype, "setItem");
    server.use(
      http.post("/api/v1/auth/login", () => HttpResponse.json({ access_token: "tok123" })),
    );
    const data = await apiPost<{ access_token: string }>("/api/v1/auth/login", {
      email_or_phone: "a@example.com",
      password: "pw",
    });
    setAccessToken(data.access_token);
    expect(setItemSpy).not.toHaveBeenCalled();
    setItemSpy.mockRestore();
  });

  it("sends credentials: include so the refresh cookie rides along", async () => {
    server.use(
      http.get("/api/v1/thing", ({ request }) => {
        expect(request.credentials).toBe("include");
        return HttpResponse.json({ ok: true });
      }),
    );
    await apiGet("/api/v1/thing");
  });

  it("apiGet returns parsed json on 200", async () => {
    server.use(http.get("/api/v1/thing", () => HttpResponse.json({ hello: "world" })));
    const result = await apiGet<{ hello: string }>("/api/v1/thing");
    expect(result).toEqual({ hello: "world" });
  });

  it("apiGet attaches bearer token when set", async () => {
    setAccessToken("mytoken");
    server.use(
      http.get("/api/v1/thing", ({ request }) => {
        expect(request.headers.get("Authorization")).toBe("Bearer mytoken");
        return HttpResponse.json({ ok: true });
      }),
    );
    await apiGet("/api/v1/thing");
  });

  it("apiGet throws structured error on non-ok response", async () => {
    server.use(
      http.get("/api/v1/thing", () =>
        HttpResponse.json(
          { error: { code: "NASA_UNAVAILABLE", message: "down" } },
          { status: 502 },
        ),
      ),
    );
    await expect(apiGet("/api/v1/thing")).rejects.toMatchObject({
      code: "NASA_UNAVAILABLE",
      message: "down",
      status: 502,
    });
  });

  it("apiGet falls back to INTERNAL_ERROR when body has no error field", async () => {
    server.use(
      http.get("/api/v1/thing", () => new HttpResponse("boom", { status: 500 })),
    );
    await expect(apiGet("/api/v1/thing")).rejects.toMatchObject({
      code: "INTERNAL_ERROR",
      status: 500,
    });
  });

  it("apiPost sends JSON body", async () => {
    server.use(
      http.post("/api/v1/thing", async ({ request }) => {
        const body = (await request.json()) as { name: string };
        expect(body.name).toBe("Ada");
        return HttpResponse.json({ ok: true });
      }),
    );
    const result = await apiPost<{ ok: boolean }>("/api/v1/thing", { name: "Ada" });
    expect(result.ok).toBe(true);
  });

  it("refreshes the access token and retries once on 401", async () => {
    setAccessToken("expired-token");
    let thingCalls = 0;
    server.use(
      http.get("/api/v1/thing", ({ request }) => {
        thingCalls += 1;
        const auth = request.headers.get("Authorization");
        if (auth === "Bearer expired-token") {
          return new HttpResponse(null, { status: 401 });
        }
        expect(auth).toBe("Bearer refreshed-token");
        return HttpResponse.json({ ok: true });
      }),
      http.post("/api/v1/auth/refresh", () => HttpResponse.json({ access_token: "refreshed-token" })),
    );

    const result = await apiGet<{ ok: boolean }>("/api/v1/thing");
    expect(result).toEqual({ ok: true });
    expect(thingCalls).toBe(2);
    expect(getAccessToken()).toBe("refreshed-token");
  });

  it("clears the access token and surfaces 401 when refresh fails", async () => {
    setAccessToken("expired-token");
    server.use(
      http.get("/api/v1/thing", () => new HttpResponse(null, { status: 401 })),
      http.post("/api/v1/auth/refresh", () => new HttpResponse(null, { status: 401 })),
    );

    await expect(apiGet("/api/v1/thing")).rejects.toMatchObject({ status: 401 });
    expect(getAccessToken()).toBeNull();
  });

  it("apiDelete returns undefined for 204 No Content", async () => {
    server.use(
      http.delete("/api/v1/thing/1", () => new HttpResponse(null, { status: 204 })),
    );
    const result = await apiDelete("/api/v1/thing/1");
    expect(result).toBeUndefined();
  });

  it("apiDelete returns parsed json for non-204 success", async () => {
    server.use(
      http.delete("/api/v1/thing/1", () => HttpResponse.json({ deleted: true }, { status: 200 })),
    );
    const result = await apiDelete<{ deleted: boolean }>("/api/v1/thing/1");
    expect(result).toEqual({ deleted: true });
  });

  it("apiDelete throws structured error on non-ok response", async () => {
    server.use(
      http.delete("/api/v1/thing/1", () =>
        HttpResponse.json(
          { error: { code: "NOT_FOUND", message: "not found" } },
          { status: 404 },
        ),
      ),
    );
    await expect(apiDelete("/api/v1/thing/1")).rejects.toMatchObject({
      code: "NOT_FOUND",
      status: 404,
    });
  });

  it("apiPost surfaces error via detail.error branch (FastAPI HTTPException)", async () => {
    server.use(
      http.post("/api/v1/thing", () =>
        HttpResponse.json(
          { detail: { error: { code: "INVALID_DATE", message: "bad" } } },
          { status: 400 },
        ),
      ),
    );
    await expect(apiPost("/api/v1/thing", {})).rejects.toMatchObject({
      code: "INVALID_DATE",
      status: 400,
    });
  });
});
