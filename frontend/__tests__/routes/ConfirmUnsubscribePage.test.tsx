import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, it, expect } from "vitest";
import ConfirmUnsubscribePage from "@/routes/ConfirmUnsubscribePage";
import { renderWithProviders } from "@/testUtils";
import { server } from "@/msw/server";

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
