import { describe, expect, it } from "vitest";
import { http, HttpResponse } from "msw";
import { server } from "../../src/msw/server";
import { fetchMissionIndex, fetchMissionSpec } from "@/solar/mission";

describe("fetchMissionIndex", () => {
  it("resolves the parsed index on a 200 response", async () => {
    const index = { missions: [{ slug: "apollo-11", name_key: "missions.apollo11.name" }] };
    server.use(http.get("/missions/index.json", () => HttpResponse.json(index)));
    await expect(fetchMissionIndex()).resolves.toEqual(index);
  });

  it("throws with the status code on a non-OK response", async () => {
    server.use(http.get("/missions/index.json", () => new HttpResponse(null, { status: 500 })));
    await expect(fetchMissionIndex()).rejects.toThrow("500");
  });
});

describe("fetchMissionSpec", () => {
  it("resolves the parsed spec for the requested slug", async () => {
    const spec = { slug: "apollo-11", name_key: "missions.apollo11.name" };
    server.use(http.get("/missions/apollo-11.json", () => HttpResponse.json(spec)));
    await expect(fetchMissionSpec("apollo-11")).resolves.toEqual(spec);
  });

  it("URL-encodes the slug and throws with the status code on a non-OK response", async () => {
    server.use(http.get("/missions/mystery%20mission.json", () => new HttpResponse(null, { status: 404 })));
    await expect(fetchMissionSpec("mystery mission")).rejects.toThrow("404");
  });
});
