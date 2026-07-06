import { screen, waitFor, act } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, it, expect, beforeEach, afterEach } from "vitest";
import SettingsPage from "@/routes/SettingsPage";
import { renderWithProviders } from "@/testUtils";
import { server } from "@/msw/server";
import i18n from "@/i18n";

beforeEach(() => {
  localStorage.clear();
});

afterEach(async () => {
  await act(async () => { await i18n.changeLanguage("en"); });
});

describe("SettingsPage", () => {
  it("renders the Settings heading", () => {
    renderWithProviders(<SettingsPage />);
    expect(screen.getByRole("heading", { level: 1, name: /Settings/i })).toBeInTheDocument();
  });

  it("renders all 6 language buttons", () => {
    renderWithProviders(<SettingsPage />);
    expect(screen.getByTestId("lang-button-en")).toBeInTheDocument();
    expect(screen.getByTestId("lang-button-de")).toBeInTheDocument();
    expect(screen.getByTestId("lang-button-fr")).toBeInTheDocument();
    expect(screen.getByTestId("lang-button-ja")).toBeInTheDocument();
    expect(screen.getByTestId("lang-button-ru")).toBeInTheDocument();
    expect(screen.getByTestId("lang-button-es")).toBeInTheDocument();
  });

  it("language switcher changes language immediately on click", async () => {
    const user = userEvent.setup();
    renderWithProviders(<SettingsPage />);

    await user.click(screen.getByTestId("lang-button-de"));

    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Einstellungen");
  });

  it("shows Not configured when nasa_key_set is false", async () => {
    renderWithProviders(<SettingsPage />);
    await waitFor(() => {
      expect(screen.getByTestId("nasa-key-status")).toHaveTextContent(/Not configured/i);
    });
  });

  it("shows Key configured when nasa_key_set is true", async () => {
    server.use(
      http.get("/api/v1/settings", () =>
        HttpResponse.json({ nasa_key_set: true, n2yo_key_set: false }),
      ),
    );
    renderWithProviders(<SettingsPage />);
    await waitFor(() => {
      expect(screen.getByTestId("nasa-key-status")).toHaveTextContent(/Key configured/i);
    });
  });

  it("shows Not configured for n2yo when n2yo_key_set is false", async () => {
    renderWithProviders(<SettingsPage />);
    await waitFor(() => {
      expect(screen.getByTestId("n2yo-key-status")).toHaveTextContent(/Not configured/i);
    });
  });

  it("shows Key configured for n2yo when n2yo_key_set is true", async () => {
    server.use(
      http.get("/api/v1/settings", () =>
        HttpResponse.json({ nasa_key_set: false, n2yo_key_set: true }),
      ),
    );
    renderWithProviders(<SettingsPage />);
    await waitFor(() => {
      expect(screen.getByTestId("n2yo-key-status")).toHaveTextContent(/Key configured/i);
    });
  });

  it("NASA key form — typing and saving POSTs key and stores in localStorage", async () => {
    let postedBody: unknown = null;
    server.use(
      http.post("/api/v1/settings/nasa-api-key", async ({ request }) => {
        postedBody = await request.json();
        return HttpResponse.json({ message: "NASA API key updated" });
      }),
    );

    const user = userEvent.setup();
    renderWithProviders(<SettingsPage />);

    await user.type(screen.getByTestId("nasa-key-input"), "my-nasa-key");
    await user.click(screen.getByTestId("nasa-key-save"));

    await waitFor(() => {
      expect(postedBody).toMatchObject({ api_key: "my-nasa-key" });
    });
    expect(localStorage.getItem("space-adventures-nasa-key")).toBe("my-nasa-key");
  });

  it("N2YO key form — typing and saving POSTs key and stores in localStorage", async () => {
    let postedBody: unknown = null;
    server.use(
      http.post("/api/v1/settings/n2yo-api-key", async ({ request }) => {
        postedBody = await request.json();
        return HttpResponse.json({ message: "N2YO API key updated" });
      }),
    );

    const user = userEvent.setup();
    renderWithProviders(<SettingsPage />);

    await user.type(screen.getByTestId("n2yo-key-input"), "my-n2yo-key");
    await user.click(screen.getByTestId("n2yo-key-save"));

    await waitFor(() => {
      expect(postedBody).toMatchObject({ api_key: "my-n2yo-key" });
    });
    expect(localStorage.getItem("space-adventures-n2yo-key")).toBe("my-n2yo-key");
  });

  it("shows Saved indicator after successful NASA key save", async () => {
    const user = userEvent.setup();
    renderWithProviders(<SettingsPage />);

    await user.type(screen.getByTestId("nasa-key-input"), "key");
    await user.click(screen.getByTestId("nasa-key-save"));

    expect(await screen.findByTestId("nasa-key-saved")).toBeInTheDocument();
    expect(screen.getByTestId("nasa-key-saved")).toHaveTextContent(/Saved/i);
  });

  it("shows Saved indicator after successful N2YO key save", async () => {
    const user = userEvent.setup();
    renderWithProviders(<SettingsPage />);

    await user.type(screen.getByTestId("n2yo-key-input"), "key");
    await user.click(screen.getByTestId("n2yo-key-save"));

    expect(await screen.findByTestId("n2yo-key-saved")).toBeInTheDocument();
  });

  it("shows error indicator when NASA key save fails", async () => {
    server.use(
      http.post("/api/v1/settings/nasa-api-key", () =>
        HttpResponse.json(
          { error: { code: "INTERNAL_ERROR", message: "Server error" } },
          { status: 500 },
        ),
      ),
    );

    const user = userEvent.setup();
    renderWithProviders(<SettingsPage />);

    await user.type(screen.getByTestId("nasa-key-input"), "key");
    await user.click(screen.getByTestId("nasa-key-save"));

    expect(await screen.findByTestId("nasa-key-error")).toBeInTheDocument();
    expect(screen.getByTestId("nasa-key-error")).toHaveTextContent(/Failed to save/i);
  });

  it("shows error indicator when N2YO key save fails", async () => {
    server.use(
      http.post("/api/v1/settings/n2yo-api-key", () =>
        HttpResponse.json(
          { error: { code: "INTERNAL_ERROR", message: "Server error" } },
          { status: 500 },
        ),
      ),
    );

    const user = userEvent.setup();
    renderWithProviders(<SettingsPage />);

    await user.type(screen.getByTestId("n2yo-key-input"), "key");
    await user.click(screen.getByTestId("n2yo-key-save"));

    expect(await screen.findByTestId("n2yo-key-error")).toBeInTheDocument();
  });

  it("pre-fills inputs from localStorage on mount", () => {
    localStorage.setItem("space-adventures-nasa-key", "stored-nasa-key");
    localStorage.setItem("space-adventures-n2yo-key", "stored-n2yo-key");

    renderWithProviders(<SettingsPage />);

    // Password inputs have value attribute even when masked
    expect(screen.getByTestId("nasa-key-input")).toHaveValue("stored-nasa-key");
    expect(screen.getByTestId("n2yo-key-input")).toHaveValue("stored-n2yo-key");
  });

  it("locale switching — German title appears after changing language to de", async () => {
    renderWithProviders(<SettingsPage />);
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Settings");

    await act(async () => { await i18n.changeLanguage("de"); });
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Einstellungen");
  });
});
