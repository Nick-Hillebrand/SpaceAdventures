import { screen, waitFor, within, act } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import Navbar from "@/components/Navbar";
import { renderWithProviders } from "@/testUtils";
import { server } from "@/msw/server";
import i18n from "@/i18n";

// P28: use vi.hoisted() for variables referenced in mock factories
const mockNavigate = vi.hoisted(() => vi.fn());

vi.mock("react-router-dom", async (importOriginal) => {
  const actual = await importOriginal<typeof import("react-router-dom")>();
  return {
    ...actual,
    useNavigate: () => mockNavigate,
    Link: actual.Link,
  };
});

beforeEach(() => {
  mockNavigate.mockClear();
  localStorage.clear();
});

afterEach(async () => {
  await act(async () => { await i18n.changeLanguage("en"); });
});

describe("Navbar", () => {
  it('shows "Log In" when not authenticated', async () => {
    server.use(
      http.get("/api/v1/auth/me", () =>
        HttpResponse.json(
          { error: { code: "UNAUTHORIZED", message: "Not authenticated" } },
          { status: 401 },
        ),
      ),
    );

    renderWithProviders(<Navbar />);

    expect(await screen.findByRole("link", { name: /Log In/i })).toBeInTheDocument();
  });

  it("shows initials when authenticated", async () => {
    renderWithProviders(<Navbar />);

    // Default mock returns Alice Liddell → initials "AL"
    expect(await screen.findByRole("button", { name: /User menu/i })).toHaveTextContent("AL");
  });

  it('clicking "Log Out" clears tokens and navigates home', async () => {
    localStorage.setItem("space-adventures-access-token", "some-token");
    localStorage.setItem("space-adventures-refresh-token", "some-refresh");

    const user = userEvent.setup();
    renderWithProviders(<Navbar />);

    // Wait for user to load
    await screen.findByRole("button", { name: /User menu/i });
    await user.click(screen.getByRole("button", { name: /User menu/i }));

    // The Log Out button has role="menuitem"
    const logoutBtn = await screen.findByRole("menuitem", { name: /Log Out/i });
    await user.click(logoutBtn);

    expect(localStorage.getItem("space-adventures-access-token")).toBeNull();
    expect(localStorage.getItem("space-adventures-refresh-token")).toBeNull();
    expect(mockNavigate).toHaveBeenCalledWith("/");
  });

  it("locale switching — German Log In link appears after changing language to de", async () => {
    server.use(
      http.get("/api/v1/auth/me", () =>
        HttpResponse.json(
          { error: { code: "UNAUTHORIZED", message: "Not authenticated" } },
          { status: 401 },
        ),
      ),
    );

    renderWithProviders(<Navbar />);
    expect(await screen.findByRole("link", { name: /Log In/i })).toBeInTheDocument();

    await act(async () => { await i18n.changeLanguage("de"); });
    expect(screen.getByRole("link", { name: /Anmelden/i })).toBeInTheDocument();
  });

  it('"My Account" link navigates to /account', async () => {
    const user = userEvent.setup();
    renderWithProviders(<Navbar />);

    await screen.findByRole("button", { name: /User menu/i });
    await user.click(screen.getByRole("button", { name: /User menu/i }));

    // The dropdown has role="menu" with a link inside it
    // Use getByRole which works synchronously after click
    await waitFor(() => {
      const myAccountLink = screen.getByRole("menuitem", { name: /My Account/i });
      expect(myAccountLink).toHaveAttribute("href", "/account");
    });
  });
});
