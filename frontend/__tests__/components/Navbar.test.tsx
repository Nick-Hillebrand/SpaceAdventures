import { screen, waitFor, within, act, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import Navbar from "@/components/Navbar";
import { renderWithProviders } from "@/testUtils";
import { server } from "@/msw/server";
import i18n from "@/i18n";
import { getAccessToken, setAccessToken } from "@/lib/api";

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
  setAccessToken(null);
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

  it('clicking "Log Out" clears the in-memory token, revokes server-side, and navigates home', async () => {
    setAccessToken("some-token");
    let logoutCalled = false;
    server.use(
      http.post("/api/v1/auth/logout", () => {
        logoutCalled = true;
        return HttpResponse.json({ message: "Logged out" });
      }),
    );

    const user = userEvent.setup();
    renderWithProviders(<Navbar />);

    // Wait for user to load
    await screen.findByRole("button", { name: /User menu/i });
    await user.click(screen.getByRole("button", { name: /User menu/i }));

    // The Log Out button has role="menuitem"
    const logoutBtn = await screen.findByRole("menuitem", { name: /Log Out/i });
    await user.click(logoutBtn);

    await waitFor(() => expect(mockNavigate).toHaveBeenCalledWith("/"));
    expect(getAccessToken()).toBeNull();
    expect(logoutCalled).toBe(true);
    expect(localStorage.getItem("space-adventures-access-token")).toBeNull();
    expect(localStorage.getItem("space-adventures-refresh-token")).toBeNull();
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

  it("opens the language menu and marks the active language", async () => {
    const user = userEvent.setup();
    renderWithProviders(<Navbar />);

    await user.click(screen.getByRole("button", { name: /Change language/i }));

    const menu = screen.getByRole("menu");
    const enOption = within(menu).getByRole("menuitem", { name: /English/i });
    const deOption = within(menu).getByRole("menuitem", { name: /Deutsch/i });
    expect(enOption).toHaveClass("lang-option--active");
    expect(deOption).not.toHaveClass("lang-option--active");
  });

  it("selecting a language from the menu changes it and closes the menu", async () => {
    const user = userEvent.setup();
    renderWithProviders(<Navbar />);

    await user.click(screen.getByRole("button", { name: /Change language/i }));
    await user.click(screen.getByRole("menuitem", { name: /Deutsch/i }));

    await waitFor(() => expect(screen.queryByRole("menu")).toBeNull());
    // aria-label is now translated too (that's the i18n fix), so after
    // switching to German the button's accessible name is "Sprache ändern".
    await waitFor(() => expect(screen.getByRole("button", { name: /Sprache ändern/i })).toHaveTextContent("DE"));
  });

  it("closes the language menu on blur when focus leaves the switcher", async () => {
    const user = userEvent.setup();
    renderWithProviders(<Navbar />);

    const langBtn = screen.getByRole("button", { name: /Change language/i });
    await user.click(langBtn);
    const switcher = langBtn.closest(".lang-switcher") as HTMLElement;

    fireEvent.blur(switcher, { relatedTarget: document.body });

    await waitFor(() => expect(screen.queryByRole("menu")).toBeNull());
  });

  it("keeps the language menu open on blur when focus moves inside the switcher", async () => {
    const user = userEvent.setup();
    renderWithProviders(<Navbar />);

    const langBtn = screen.getByRole("button", { name: /Change language/i });
    await user.click(langBtn);
    const switcher = langBtn.closest(".lang-switcher") as HTMLElement;
    const enOption = screen.getByRole("menuitem", { name: /English/i });

    fireEvent.blur(switcher, { relatedTarget: enOption });

    expect(screen.getByRole("menu")).toBeInTheDocument();
  });
});
