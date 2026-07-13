import { screen, waitFor, act } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import LoginPage from "@/routes/LoginPage";
import { renderWithProviders } from "@/testUtils";
import { server } from "@/msw/server";
import i18n from "@/i18n";
import { getAccessToken, setAccessToken } from "@/lib/api";

// P28: use vi.hoisted() for variables referenced in mock factories
const { mockNavigate, mockLocation } = vi.hoisted(() => ({
  mockNavigate: vi.fn(),
  mockLocation: vi.fn().mockReturnValue({ search: "" }),
}));

vi.mock("react-router-dom", async (importOriginal) => {
  const actual = await importOriginal<typeof import("react-router-dom")>();
  return {
    ...actual,
    useNavigate: () => mockNavigate,
    useLocation: mockLocation,
  };
});

beforeEach(() => {
  mockNavigate.mockClear();
  mockLocation.mockReturnValue({ search: "" });
  localStorage.clear();
  setAccessToken(null);
});

afterEach(async () => {
  await act(async () => { await i18n.changeLanguage("en"); });
});

describe("LoginPage", () => {
  it("happy path — renders form, submits, stores the access token in memory, redirects", async () => {
    const user = userEvent.setup();
    renderWithProviders(<LoginPage />);

    await user.type(screen.getByLabelText(/Email or Phone/i), "alice@example.com");
    await user.type(screen.getByLabelText(/^Password$/i), "securepassword");
    await user.click(screen.getByRole("button", { name: /Log In/i }));

    await waitFor(() => {
      expect(mockNavigate).toHaveBeenCalledWith("/");
    });

    // Access token lives in memory only; the refresh token rides in a
    // server-set httpOnly cookie invisible to JS — neither touches
    // localStorage (P1.4).
    expect(getAccessToken()).toBe("test-access-token");
    expect(localStorage.getItem("space-adventures-access-token")).toBeNull();
    expect(localStorage.getItem("space-adventures-refresh-token")).toBeNull();
  });

  it("loading state — submit button shows loading text while submitting", async () => {
    server.use(
      http.post("/api/v1/auth/login", async () => {
        await new Promise((resolve) => setTimeout(resolve, 100));
        return HttpResponse.json({ access_token: "tok", refresh_token: "ref" });
      }),
    );

    const user = userEvent.setup();
    renderWithProviders(<LoginPage />);

    await user.type(screen.getByLabelText(/Email or Phone/i), "alice@example.com");
    await user.type(screen.getByLabelText(/^Password$/i), "securepassword");
    await user.click(screen.getByRole("button", { name: /Log In/i }));

    expect(screen.getByRole("button", { name: /Logging in/i })).toBeInTheDocument();
    await waitFor(() => expect(mockNavigate).toHaveBeenCalled());
  });

  it("error state — API error shows banner", async () => {
    server.use(
      http.post("/api/v1/auth/login", () =>
        HttpResponse.json(
          { error: { code: "LOGIN_FAILED", message: "Invalid credentials" } },
          { status: 401 },
        ),
      ),
    );

    const user = userEvent.setup();
    renderWithProviders(<LoginPage />);

    await user.type(screen.getByLabelText(/Email or Phone/i), "alice@example.com");
    await user.type(screen.getByLabelText(/^Password$/i), "wrongpassword");
    await user.click(screen.getByRole("button", { name: /Log In/i }));

    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent(/Invalid credentials/i);
  });

  it("open redirect rejected — ?return=https://evil.com → redirects to /", async () => {
    mockLocation.mockReturnValue({ search: "?return=https%3A%2F%2Fevil.com" });

    const user = userEvent.setup();
    renderWithProviders(<LoginPage />);

    await user.type(screen.getByLabelText(/Email or Phone/i), "alice@example.com");
    await user.type(screen.getByLabelText(/^Password$/i), "securepassword");
    await user.click(screen.getByRole("button", { name: /Log In/i }));

    await waitFor(() => {
      expect(mockNavigate).toHaveBeenCalledWith("/");
    });
  });

  it("valid internal return — ?return=/launches → redirects to /launches", async () => {
    mockLocation.mockReturnValue({ search: "?return=%2Flaunches" });

    const user = userEvent.setup();
    renderWithProviders(<LoginPage />);

    await user.type(screen.getByLabelText(/Email or Phone/i), "alice@example.com");
    await user.type(screen.getByLabelText(/^Password$/i), "securepassword");
    await user.click(screen.getByRole("button", { name: /Log In/i }));

    await waitFor(() => {
      expect(mockNavigate).toHaveBeenCalledWith("/launches");
    });
  });

  it("link to register visible", () => {
    renderWithProviders(<LoginPage />);
    expect(screen.getByRole("link", { name: /Register/i })).toBeInTheDocument();
  });

  it("toggling the show-password button reveals and re-hides the password", async () => {
    const user = userEvent.setup();
    renderWithProviders(<LoginPage />);

    const passwordInput = screen.getByLabelText(/^Password$/i);
    expect(passwordInput).toHaveAttribute("type", "password");

    const toggleBtn = screen.getByRole("button", { name: /Show password/i });
    await user.click(toggleBtn);
    expect(passwordInput).toHaveAttribute("type", "text");

    await user.click(screen.getByRole("button", { name: /Hide password/i }));
    expect(passwordInput).toHaveAttribute("type", "password");
  });

  it("locale switching — German title appears after changing language to de", async () => {
    renderWithProviders(<LoginPage />);
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Log In");

    await act(async () => { await i18n.changeLanguage("de"); });
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Anmelden");
  });
});
