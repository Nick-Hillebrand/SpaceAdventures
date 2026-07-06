import { screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import EmptyState from "@/components/EmptyState";
import { renderWithProviders } from "@/testUtils";

describe("EmptyState", () => {
  it("renders the message text", () => {
    renderWithProviders(<EmptyState message="Nothing here yet" />);
    expect(screen.getByText("Nothing here yet")).toBeInTheDocument();
  });

  it("renders the empty-state container", () => {
    renderWithProviders(<EmptyState message="Empty" />);
    expect(screen.getByTestId("empty-state")).toBeInTheDocument();
  });

  it("renders an SVG illustration", () => {
    const { container } = renderWithProviders(<EmptyState message="Empty" />);
    expect(container.querySelector("svg")).toBeInTheDocument();
  });
});
