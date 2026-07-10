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

  it("does not render API-key input fields (keys are server-managed)", () => {
    renderWithProviders(<SettingsPage />);
    expect(screen.queryByTestId("nasa-key-input")).not.toBeInTheDocument();
    expect(screen.queryByTestId("n2yo-key-input")).not.toBeInTheDocument();
    expect(screen.queryByTestId("nasa-key-save")).not.toBeInTheDocument();
    expect(screen.queryByTestId("n2yo-key-save")).not.toBeInTheDocument();
  });

  it("shows the server-managed hint", () => {
    renderWithProviders(<SettingsPage />);
    expect(screen.getByTestId("settings-key-hint")).toHaveTextContent(
      /configured on the server/i,
    );
  });

  it("locale switching — German title appears after changing language to de", async () => {
    renderWithProviders(<SettingsPage />);
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Settings");

    await act(async () => { await i18n.changeLanguage("de"); });
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Einstellungen");
  });
});
