import { screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import MissionsIndexPage from "@/routes/MissionsIndexPage";
import { renderWithProviders } from "@/testUtils";
import { server } from "@/msw/server";

describe("MissionsIndexPage", () => {
  it("shows a loading state, then a list of missions linking to their detail routes", async () => {
    server.use(
      http.get("/missions/index.json", () =>
        HttpResponse.json({
          missions: [
            { slug: "apollo-11", name_key: "missions.apollo11.name" },
            { slug: "mars-pathfinder", name_key: "missions.marsPathfinder.name" },
          ],
        }),
      ),
    );

    renderWithProviders(<MissionsIndexPage />);

    expect(screen.getByText(/Loading missions/i)).toBeInTheDocument();

    const apollo = await screen.findByRole("link", { name: /Apollo 11/i });
    expect(apollo).toHaveAttribute("href", "/missions/apollo-11");

    const pathfinder = screen.getByRole("link", { name: /Mars Pathfinder/i });
    expect(pathfinder).toHaveAttribute("href", "/missions/mars-pathfinder");
  });

  it("shows an empty state when the catalogue has no missions", async () => {
    server.use(
      http.get("/missions/index.json", () => HttpResponse.json({ missions: [] })),
    );

    renderWithProviders(<MissionsIndexPage />);

    expect(await screen.findByText(/No missions available yet/i)).toBeInTheDocument();
  });

  it("shows an error state when the index fails to load", async () => {
    server.use(
      http.get("/missions/index.json", () => new HttpResponse(null, { status: 500 })),
    );

    renderWithProviders(<MissionsIndexPage />);

    expect(await screen.findByText(/This mission could not be loaded/i)).toBeInTheDocument();
  });
});
