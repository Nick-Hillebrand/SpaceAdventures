import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { http, HttpResponse } from "msw";
import { server } from "@/msw/server";
import {
  apiGet,
  apiDelete,
  apiPost,
  getAccessToken,
  setAccessToken,
  getRefreshToken,
  setRefreshToken,
} from "@/lib/api";

describe("api helpers", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  afterEach(() => {
    localStorage.clear();
  });

  it("stores and reads the access token", () => {
    setAccessToken("abc");
    expect(getAccessToken()).toBe("abc");
    setAccessToken(null);
    expect(getAccessToken()).toBeNull();
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

  it("setRefreshToken(null) removes the refresh token key", () => {
    setRefreshToken("my-refresh");
    expect(getRefreshToken()).toBe("my-refresh");
    setRefreshToken(null);
    expect(getRefreshToken()).toBeNull();
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
