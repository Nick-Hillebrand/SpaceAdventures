import { screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import Skeleton from "@/components/Skeleton";
import { renderWithProviders } from "@/testUtils";

describe("Skeleton", () => {
  it("renders with skeleton-block class", () => {
    const { container } = renderWithProviders(<Skeleton />);
    expect(container.querySelector(".skeleton-block")).toBeInTheDocument();
  });

  it("applies custom width and height via style", () => {
    const { container } = renderWithProviders(<Skeleton width="200px" height="3rem" />);
    const el = container.querySelector(".skeleton-block") as HTMLElement;
    expect(el.style.width).toBe("200px");
    expect(el.style.height).toBe("3rem");
  });

  it("is hidden from screen readers", () => {
    const { container } = renderWithProviders(<Skeleton />);
    const el = container.querySelector(".skeleton-block");
    expect(el).toHaveAttribute("aria-hidden", "true");
  });
});
