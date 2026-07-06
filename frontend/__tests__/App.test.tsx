import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { http, HttpResponse } from "msw";
import { server } from "@/msw/server";
import App from "@/App";

describe("App", () => {
  it("renders the navbar brand link", () => {
    server.use(http.get("/api/v1/apod", () => HttpResponse.json(null)));
    render(<App />);
    expect(screen.getByRole("link", { name: /Space Adventures/i })).toBeInTheDocument();
  });
});
