import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, it, expect, vi } from "vitest";
import AccountPage from "@/routes/AccountPage";
import { renderWithProviders } from "@/testUtils";
import { server } from "@/msw/server";

// P28: use vi.hoisted() for variables referenced in mock factories
const mockNavigate = vi.hoisted(() => vi.fn());

vi.mock("react-router-dom", async (importOriginal) => {
  const actual = await importOriginal<typeof import("react-router-dom")>();
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  };
});

describe("AccountPage", () => {
  it("redirects to login when not authenticated", async () => {
    server.use(
      http.get("/api/v1/auth/me", () =>
        HttpResponse.json(
          { error: { code: "UNAUTHORIZED", message: "Not authenticated" } },
          { status: 401 },
        ),
      ),
    );

    renderWithProviders(<AccountPage />);

    await waitFor(() => {
      expect(mockNavigate).toHaveBeenCalledWith("/login?return=/account");
    });
  });

  it("shows user info on profile tab", async () => {
    renderWithProviders(<AccountPage />);

    expect(await screen.findByText(/Alice Liddell/i)).toBeInTheDocument();
    expect(screen.getByText(/alice@example.com/i)).toBeInTheDocument();
  });

  it("shows verified badges for verified channels", async () => {
    renderWithProviders(<AccountPage />);

    // email_verified: true in default mock
    expect(await screen.findByLabelText(/email verified/i)).toBeInTheDocument();
  });

  it("resend OTP button only shown when not verified", async () => {
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

    renderWithProviders(<AccountPage />);

    // Both should have resend buttons
    const resendButtons = await screen.findAllByRole("button", { name: /Resend OTP/i });
    expect(resendButtons.length).toBeGreaterThanOrEqual(1);
  });

  it("subscriptions tab shows list", async () => {
    server.use(
      http.get("/api/v1/subscriptions", () =>
        HttpResponse.json([
          {
            id: "sub-001",
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

    const user = userEvent.setup();
    renderWithProviders(<AccountPage />);

    await screen.findByText(/Alice Liddell/i);

    await user.click(screen.getByRole("button", { name: /Subscriptions/i }));

    expect(await screen.findByTestId("subscriptions-list")).toBeInTheDocument();
    expect(screen.getByText(/launch-001/i)).toBeInTheDocument();
  });

  it("subscriptions tab shows empty state", async () => {
    const user = userEvent.setup();
    renderWithProviders(<AccountPage />);

    await screen.findByText(/Alice Liddell/i);

    await user.click(screen.getByRole("button", { name: /Subscriptions/i }));

    expect(await screen.findByTestId("no-subscriptions")).toBeInTheDocument();
  });

  it("delete button calls DELETE endpoint", async () => {
    let deleteCalledId: string | null = null;
    server.use(
      http.get("/api/v1/subscriptions", () =>
        HttpResponse.json([
          {
            id: "sub-del-001",
            type: "agency",
            ll2_id: null,
            agency_name: "SpaceX",
            notify_email: false,
            notify_sms: true,
            created_at: "2026-01-01T00:00:00Z",
          },
        ]),
      ),
      http.delete("/api/v1/subscriptions/:id", ({ params }) => {
        deleteCalledId = params.id as string;
        return new HttpResponse(null, { status: 204 });
      }),
    );

    const user = userEvent.setup();
    renderWithProviders(<AccountPage />);

    await screen.findByText(/Alice Liddell/i);
    await user.click(screen.getByRole("button", { name: /Subscriptions/i }));

    const deleteBtn = await screen.findByTestId("delete-sub-sub-del-001");
    await user.click(deleteBtn);

    await waitFor(() => {
      expect(deleteCalledId).toBe("sub-del-001");
    });
  });
});
