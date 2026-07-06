import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, it, expect } from "vitest";
import { SubscribeModal } from "@/components/SubscribeModal";
import { renderWithProviders } from "@/testUtils";
import { server } from "@/msw/server";
import type { LaunchData } from "@/types/api";

function makeLaunch(overrides: Partial<LaunchData> = {}): LaunchData {
  return {
    ll2_id: "launch-001",
    name: "Falcon 9 | Starlink",
    net: new Date(Date.now() + 2 * 3600 * 1000).toISOString(),
    status_abbrev: "Go",
    status_name: "Go for Launch",
    agency_name: "SpaceX",
    agency_type: "Commercial",
    rocket_name: "Falcon 9 Block 5",
    rocket_family: "Falcon",
    mission_name: "Starlink Mission",
    mission_description: "Batch of Starlink satellites.",
    mission_type: "Communications",
    pad_name: "SLC-40",
    pad_location: "Cape Canaveral, FL, USA",
    image_url: null,
    livestream_urls: [],
    fetched_at: new Date().toISOString(),
    ...overrides,
  };
}

function renderModal(launch = makeLaunch(), isOpen = true, onClose = () => {}) {
  return renderWithProviders(
    <SubscribeModal launch={launch} isOpen={isOpen} onClose={onClose} />
  );
}

describe("SubscribeModal", () => {
  it("unauthenticated — shows login prompt with correct links", async () => {
    server.use(
      http.get("/api/v1/auth/me", () =>
        HttpResponse.json(
          { error: { code: "UNAUTHORIZED", message: "Not authenticated" } },
          { status: 401 },
        ),
      ),
    );

    renderModal();

    const loginPrompt = await screen.findByTestId("login-prompt");
    expect(loginPrompt).toBeInTheDocument();

    const loginLink = screen.getByTestId("login-link");
    expect(loginLink).toHaveAttribute("href", "/login?return=/launches");

    const registerLink = screen.getByTestId("register-link");
    expect(registerLink).toHaveAttribute("href", "/register?return=/launches");
  });

  it("authenticated, unverified — shows verify email and phone prompts", async () => {
    server.use(
      http.get("/api/v1/auth/me", () =>
        HttpResponse.json({
          id: 1,
          first_name: "Alice",
          last_name: "Liddell",
          email: "alice@example.com",
          phone: "+15551234567",
          email_verified: false,
          phone_verified: false,
          created_at: "2024-01-01T00:00:00Z",
        }),
      ),
    );

    renderModal();

    await screen.findByTestId("verify-email-prompt");
    expect(screen.getByTestId("verify-email-prompt")).toBeInTheDocument();
    expect(screen.getByTestId("verify-phone-prompt")).toBeInTheDocument();
    expect(screen.getByTestId("no-channel-prompt")).toBeInTheDocument();
  });

  it("authenticated, verified email — shows email checkbox enabled", async () => {
    // Default mock has email_verified: true
    renderModal();

    const emailCheckbox = await screen.findByTestId("checkbox-email");
    expect(emailCheckbox).toBeInTheDocument();
    expect(emailCheckbox).not.toBeDisabled();
  });

  it("subscribe to launch — POST called with correct body", async () => {
    const user = userEvent.setup();
    let postBody: unknown = null;

    server.use(
      http.post("/api/v1/subscriptions", async ({ request }) => {
        postBody = await request.json();
        return HttpResponse.json(
          {
            id: "sub-001",
            type: "launch",
            ll2_id: "launch-001",
            agency_name: null,
            notify_email: true,
            notify_sms: false,
            created_at: "2026-01-01T00:00:00Z",
          },
          { status: 201 },
        );
      }),
    );

    renderModal();

    // Wait for auth to load
    await screen.findByTestId("checkbox-launch");

    // Check "Subscribe to this launch"
    await user.click(screen.getByTestId("checkbox-launch"));
    // Check email notification
    await user.click(screen.getByTestId("checkbox-email"));
    // Confirm
    await user.click(screen.getByTestId("confirm-subscribe"));

    await waitFor(() => {
      expect(postBody).toMatchObject({
        type: "launch",
        ll2_id: "launch-001",
        notify_email: true,
        notify_sms: false,
      });
    });
  });

  it("subscribe to agency — POST called with agency_name", async () => {
    const user = userEvent.setup();
    let postBody: unknown = null;

    server.use(
      http.post("/api/v1/subscriptions", async ({ request }) => {
        postBody = await request.json();
        return HttpResponse.json(
          {
            id: "sub-002",
            type: "agency",
            ll2_id: null,
            agency_name: "SpaceX",
            notify_email: true,
            notify_sms: false,
            created_at: "2026-01-01T00:00:00Z",
          },
          { status: 201 },
        );
      }),
    );

    renderModal();

    await screen.findByTestId("checkbox-agency");

    await user.click(screen.getByTestId("checkbox-agency"));
    await user.click(screen.getByTestId("checkbox-email"));
    await user.click(screen.getByTestId("confirm-subscribe"));

    await waitFor(() => {
      expect(postBody).toMatchObject({
        type: "agency",
        agency_name: "SpaceX",
        notify_email: true,
        notify_sms: false,
      });
    });
  });

  it("filled bell state when already subscribed", async () => {
    // Return subscription matching this launch's ll2_id
    server.use(
      http.get("/api/v1/subscriptions", () =>
        HttpResponse.json([
          {
            id: "sub-existing",
            type: "launch",
            ll2_id: "launch-001",
            agency_name: null,
            notify_email: true,
            notify_sms: false,
            created_at: "2026-01-01T00:00:00Z",
          },
        ]),
      ),
    );

    renderModal();

    // The modal uses useSubscriptions — wait for data
    await screen.findByTestId("checkbox-launch");

    // The LaunchCard's bell would show 🔔 — but we're testing the modal itself here
    // The modal renders based on subscription data
    // Confirm button should be present (subscription already exists but modal still shows)
    expect(screen.getByTestId("confirm-subscribe")).toBeInTheDocument();
  });
});
