import { screen, waitFor, act } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, it, expect, afterEach } from "vitest";
import ConfirmUnsubscribePage from "@/routes/ConfirmUnsubscribePage";
import { renderWithProviders } from "@/testUtils";
import { server } from "@/msw/server";
import i18n from "@/i18n";

afterEach(async () => {
  await act(async () => { await i18n.changeLanguage("en"); });
});

function renderPage(token = "test-token") {
  return renderWithProviders(<ConfirmUnsubscribePage />, undefined, {
    initialEntries: [`/confirm-unsubscribe?token=${token}`],
  });
}

describe("ConfirmUnsubscribePage", () => {
  it("renders confirm button with token from URL", async () => {
    renderPage("my-jwt-token");

    expect(screen.getByTestId("confirm-unsubscribe-page")).toBeInTheDocument();
    expect(screen.getByTestId("confirm-unsubscribe-button")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /Confirm Unsubscribe/i })).toBeInTheDocument();
  });

  it("on confirm click — POST called with token", async () => {
    const user = userEvent.setup();
    let capturedBody: unknown = null;

    server.use(
      http.post("/api/v1/subscriptions/unsubscribe", async ({ request }) => {
        capturedBody = await request.json();
        return HttpResponse.json({ message: "Unsubscribed successfully" });
      }),
    );

    renderPage("my-jwt-token");

    await user.click(screen.getByTestId("confirm-unsubscribe-button"));

    await waitFor(() => {
      expect(capturedBody).toMatchObject({ token: "my-jwt-token" });
    });
  });

  it("shows success message after POST", async () => {
    const user = userEvent.setup();

    renderPage("valid-token");

    await user.click(screen.getByTestId("confirm-unsubscribe-button"));

    expect(await screen.findByTestId("unsubscribe-success")).toBeInTheDocument();
    expect(screen.getByText(/You have been unsubscribed successfully/i)).toBeInTheDocument();
  });

  it("locale switching — German title appears after changing language to de", async () => {
    renderPage();
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Confirm Unsubscribe");

    await act(async () => { await i18n.changeLanguage("de"); });
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Abmeldung bestätigen");
  });

  it("renders with empty token when no query param present", () => {
    renderWithProviders(<ConfirmUnsubscribePage />, undefined, {
      initialEntries: ["/confirm-unsubscribe"],
    });
    expect(screen.getByTestId("confirm-unsubscribe-page")).toBeInTheDocument();
  });

  it("shows generic error when error has no message", async () => {
    const user = userEvent.setup();

    server.use(
      http.post("/api/v1/subscriptions/unsubscribe", () =>
        HttpResponse.json({}, { status: 500 }),
      ),
    );

    renderPage("some-token");
    await user.click(screen.getByTestId("confirm-unsubscribe-button"));

    await waitFor(() => {
      expect(screen.getByTestId("unsubscribe-error")).toBeInTheDocument();
    });
  });

  it("shows error message on POST failure", async () => {
    const user = userEvent.setup();

    server.use(
      http.post("/api/v1/subscriptions/unsubscribe", () =>
        HttpResponse.json(
          { error: { code: "INVALID_TOKEN", message: "Invalid or expired unsubscribe token" } },
          { status: 400 },
        ),
      ),
    );

    renderPage("bad-token");

    await user.click(screen.getByTestId("confirm-unsubscribe-button"));

    expect(await screen.findByTestId("unsubscribe-error")).toBeInTheDocument();
    expect(screen.getByTestId("unsubscribe-error").textContent).toMatch(
      /Invalid or expired|error/i,
    );
  });
});
