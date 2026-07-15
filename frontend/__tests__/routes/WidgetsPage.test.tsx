import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import WidgetsPage from "@/routes/WidgetsPage";
import { renderWithProviders } from "@/testUtils";

// jsdom sets window.location.origin to "http://localhost" (no port in older
// versions) or "http://localhost:3000" depending on the vitest config.  Derive
// it dynamically so the test is not sensitive to that default.
const EMBED_BASE = `${window.location.origin}/embed/next-launch`;

beforeEach(() => {
  vi.restoreAllMocks();
});

afterEach(() => {
  // Restore real timers in case a test switched to fake timers and failed
  // before calling vi.useRealTimers().
  vi.useRealTimers();
});

describe("WidgetsPage", () => {
  it("renders the page heading", () => {
    renderWithProviders(<WidgetsPage />);
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Embeddable Widgets");
  });

  it("renders the Next Launch Widget section", () => {
    renderWithProviders(<WidgetsPage />);
    expect(screen.getByRole("heading", { level: 2 })).toHaveTextContent("Next Launch Widget");
    expect(screen.getByTestId("next-launch-widget-section")).toBeInTheDocument();
  });

  it("renders provider input and language select", () => {
    renderWithProviders(<WidgetsPage />);
    expect(screen.getByTestId("provider-input")).toBeInTheDocument();
    expect(screen.getByTestId("lang-select")).toBeInTheDocument();
  });

  it("default embed preview src has no query params (all providers, en)", () => {
    renderWithProviders(<WidgetsPage />);
    const iframe = screen.getByTestId("embed-preview") as HTMLIFrameElement;
    expect(iframe.src).toBe(EMBED_BASE);
  });

  it("provider filter adds ?provider= to embed URL", async () => {
    const user = userEvent.setup();
    renderWithProviders(<WidgetsPage />);

    await user.type(screen.getByTestId("provider-input"), "SpaceX");
    const iframe = screen.getByTestId("embed-preview") as HTMLIFrameElement;
    expect(iframe.src).toBe(`${EMBED_BASE}?provider=SpaceX`);
  });

  it("language select adds ?lang= to embed URL (non-en only)", async () => {
    const user = userEvent.setup();
    renderWithProviders(<WidgetsPage />);

    await user.selectOptions(screen.getByTestId("lang-select"), "de");
    const iframe = screen.getByTestId("embed-preview") as HTMLIFrameElement;
    expect(iframe.src).toBe(`${EMBED_BASE}?lang=de`);
  });

  it("provider + lang both appear in embed URL", async () => {
    const user = userEvent.setup();
    renderWithProviders(<WidgetsPage />);

    await user.type(screen.getByTestId("provider-input"), "SpaceX");
    await user.selectOptions(screen.getByTestId("lang-select"), "fr");

    const iframe = screen.getByTestId("embed-preview") as HTMLIFrameElement;
    expect(iframe.src).toContain("provider=SpaceX");
    expect(iframe.src).toContain("lang=fr");
  });

  it("en lang is omitted from embed URL (it is the default)", async () => {
    const user = userEvent.setup();
    renderWithProviders(<WidgetsPage />);

    await user.selectOptions(screen.getByTestId("lang-select"), "en");
    const iframe = screen.getByTestId("embed-preview") as HTMLIFrameElement;
    // default lang=en should not appear in the URL
    expect(iframe.src).not.toContain("lang=");
  });

  it("snippet code contains the iframe src from the preview", async () => {
    const user = userEvent.setup();
    renderWithProviders(<WidgetsPage />);

    await user.type(screen.getByTestId("provider-input"), "NASA");

    const snippet = screen.getByTestId("embed-snippet").textContent ?? "";
    expect(snippet).toContain(`src="${EMBED_BASE}?provider=NASA"`);
    expect(snippet).toContain("<iframe");
    expect(snippet).toContain("</iframe>");
  });

  it("copy button writes snippet to clipboard", async () => {
    const user = userEvent.setup();
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", {
      value: { writeText },
      writable: true,
    });

    renderWithProviders(<WidgetsPage />);

    await user.click(screen.getByTestId("copy-button"));

    expect(writeText).toHaveBeenCalledOnce();
    const written = writeText.mock.calls[0][0] as string;
    expect(written).toContain("<iframe");
    expect(written).toContain(EMBED_BASE);
  });

  it("copy button shows Copied! after clicking", async () => {
    const user = userEvent.setup();
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", {
      value: { writeText },
      writable: true,
    });

    renderWithProviders(<WidgetsPage />);

    expect(screen.getByTestId("copy-button")).toHaveTextContent("Copy");
    await user.click(screen.getByTestId("copy-button"));

    // setCopied(true) fires after the clipboard promise resolves — waitFor
    // polls until the DOM update lands (no fake timers needed here).
    await waitFor(() => {
      expect(screen.getByTestId("copy-button")).toHaveTextContent("Copied!");
    });
  });

  it("snippet uses the current provider and lang combination", async () => {
    const user = userEvent.setup();
    renderWithProviders(<WidgetsPage />);

    await user.type(screen.getByTestId("provider-input"), "ESA");
    await user.selectOptions(screen.getByTestId("lang-select"), "de");

    const snippet = screen.getByTestId("embed-snippet").textContent ?? "";
    expect(snippet).toContain("provider=ESA");
    expect(snippet).toContain("lang=de");
  });

  it("language select has all 6 locales as options", () => {
    renderWithProviders(<WidgetsPage />);
    const select = screen.getByTestId("lang-select") as HTMLSelectElement;
    const codes = Array.from(select.options).map((o) => o.value);
    expect(codes).toContain("en");
    expect(codes).toContain("de");
    expect(codes).toContain("es");
    expect(codes).toContain("fr");
    expect(codes).toContain("ja");
    expect(codes).toContain("ru");
  });
});
