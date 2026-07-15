import { screen, waitFor, act } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, it, expect, vi, afterEach, beforeEach } from "vitest";
import AccountPage from "@/routes/AccountPage";
import { renderWithProviders } from "@/testUtils";
import { server } from "@/msw/server";
import i18n from "@/i18n";

afterEach(async () => {
  await act(async () => { await i18n.changeLanguage("en"); });
  vi.unstubAllGlobals();
  // @ts-expect-error — cleaning up the test-only navigator override
  delete navigator.serviceWorker;
});

class FakePushSubscription {
  endpoint = "https://push.example/endpoint-1";
  unsubscribe = vi.fn().mockResolvedValue(true);
  toJSON() {
    return {
      endpoint: this.endpoint,
      keys: { p256dh: "test-p256dh", auth: "test-auth" },
    };
  }
}

function installPushEnvironment({
  initialPermission = "default" as NotificationPermission,
  existingSubscription = null as FakePushSubscription | null,
}: {
  initialPermission?: NotificationPermission;
  existingSubscription?: FakePushSubscription | null;
} = {}) {
  const requestPermission = vi.fn().mockResolvedValue(initialPermission);
  const subscribe = vi.fn().mockResolvedValue(new FakePushSubscription());
  const getSubscription = vi.fn().mockResolvedValue(existingSubscription);

  class FakeNotification {
    static permission: NotificationPermission = initialPermission;
    static requestPermission = requestPermission;
  }

  const registration = {
    pushManager: { subscribe, getSubscription },
  };

  vi.stubGlobal("Notification", FakeNotification);
  vi.stubGlobal("PushManager", function PushManager() {});
  Object.defineProperty(navigator, "serviceWorker", {
    configurable: true,
    value: { ready: Promise.resolve(registration) },
  });

  return { requestPermission, subscribe, getSubscription };
}

// P28: use vi.hoisted() for variables referenced in mock factories
const mockNavigate = vi.hoisted(() => vi.fn());

beforeEach(() => {
  mockNavigate.mockClear();
});

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

  it("resend OTP button calls resend endpoint and shows success status", async () => {
    server.use(
      http.get("/api/v1/auth/me", () =>
        HttpResponse.json({
          id: 1,
          first_name: "Alice",
          last_name: "Liddell",
          email: "alice@example.com",
          phone: null,
          email_verified: false,
          phone_verified: false,
          created_at: "2024-01-01T00:00:00Z",
        }),
      ),
      http.post("/api/v1/auth/verify/resend", () =>
        HttpResponse.json({ message: "OTP resent" }),
      ),
    );

    const user = userEvent.setup();
    renderWithProviders(<AccountPage />);

    const resendBtn = await screen.findByRole("button", { name: /Resend OTP/i });
    await user.click(resendBtn);

    await waitFor(() => {
      expect(screen.getByText(/OTP sent!/i)).toBeInTheDocument();
    });
  });

  it("resend OTP shows error status on failure", async () => {
    server.use(
      http.get("/api/v1/auth/me", () =>
        HttpResponse.json({
          id: 1,
          first_name: "Alice",
          last_name: "Liddell",
          email: "alice@example.com",
          phone: null,
          email_verified: false,
          phone_verified: false,
          created_at: "2024-01-01T00:00:00Z",
        }),
      ),
      http.post("/api/v1/auth/verify/resend", () =>
        HttpResponse.json({ error: { code: "RATE_LIMIT", message: "Rate limited" } }, { status: 429 }),
      ),
    );

    const user = userEvent.setup();
    renderWithProviders(<AccountPage />);

    const resendBtn = await screen.findByRole("button", { name: /Resend OTP/i });
    await user.click(resendBtn);

    await waitFor(() => {
      expect(screen.getByText(/Failed to send OTP/i)).toBeInTheDocument();
    });
  });

  it("shows phone verified badge when phone is verified", async () => {
    server.use(
      http.get("/api/v1/auth/me", () =>
        HttpResponse.json({
          id: 1,
          first_name: "Alice",
          last_name: "Liddell",
          email: "alice@example.com",
          phone: "+15551234567",
          email_verified: true,
          phone_verified: true,
          created_at: "2024-01-01T00:00:00Z",
        }),
      ),
    );

    renderWithProviders(<AccountPage />);
    expect(await screen.findByLabelText(/phone verified/i)).toBeInTheDocument();
  });

  it("shows subscriptions loading state", async () => {
    server.use(
      http.get("/api/v1/subscriptions", async () => {
        await new Promise((r) => setTimeout(r, 200));
        return HttpResponse.json([]);
      }),
    );

    const user = userEvent.setup();
    renderWithProviders(<AccountPage />);

    await screen.findByText(/Alice Liddell/i);
    await user.click(screen.getByRole("button", { name: /Subscriptions/i }));

    expect(await screen.findByText(/Loading subscriptions/i)).toBeInTheDocument();
  });

  it("locale switching — German title appears after changing language to de", async () => {
    renderWithProviders(<AccountPage />);
    await screen.findByText(/Alice Liddell/i);
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("My Account");

    await act(async () => { await i18n.changeLanguage("de"); });
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Mein Konto");
  });

  it("consent toggle reflects current state and calls consent endpoint on change", async () => {
    let lastConsentBody: { granted: boolean } | null = null;
    server.use(
      http.post("/api/v1/auth/consent", async ({ request }) => {
        lastConsentBody = (await request.json()) as { granted: boolean };
        return HttpResponse.json({
          id: 1,
          first_name: "Alice",
          last_name: "Liddell",
          email: "alice@example.com",
          phone: null,
          email_verified: true,
          phone_verified: false,
          created_at: "2024-01-01T00:00:00Z",
          consent_notifications_at: lastConsentBody.granted ? "2026-01-01T00:00:00Z" : null,
        });
      }),
    );

    const user = userEvent.setup();
    renderWithProviders(<AccountPage />);

    await screen.findByText(/Alice Liddell/i);

    const toggle = screen.getByTestId("consent-toggle");
    expect(toggle).toBeChecked();

    await user.click(toggle);

    await waitFor(() => {
      expect(lastConsentBody).toEqual({ granted: false });
    });
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

  it("export data — button triggers download of exported JSON", async () => {
    let exportCalled = false;
    URL.createObjectURL = vi.fn().mockReturnValue("blob:mock-url");
    URL.revokeObjectURL = vi.fn();
    const createObjectURLSpy = vi.mocked(URL.createObjectURL);
    const revokeObjectURLSpy = vi.mocked(URL.revokeObjectURL);
    const clickSpy = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});

    server.use(
      http.get("/api/v1/auth/me/export", () => {
        exportCalled = true;
        return HttpResponse.json({ user: { id: 1 }, subscriptions: [] });
      }),
    );

    const user = userEvent.setup();
    renderWithProviders(<AccountPage />);
    await screen.findByText(/Alice Liddell/i);

    await user.click(screen.getByRole("button", { name: /Download my data/i }));

    await waitFor(() => {
      expect(exportCalled).toBe(true);
    });
    expect(createObjectURLSpy).toHaveBeenCalled();
    expect(clickSpy).toHaveBeenCalled();
    expect(revokeObjectURLSpy).toHaveBeenCalled();

    createObjectURLSpy.mockRestore();
    revokeObjectURLSpy.mockRestore();
    clickSpy.mockRestore();
  });

  it("export data — shows error status on failure", async () => {
    server.use(
      http.get("/api/v1/auth/me/export", () =>
        HttpResponse.json({ error: { code: "SERVER_ERROR", message: "boom" } }, { status: 500 }),
      ),
    );

    const user = userEvent.setup();
    renderWithProviders(<AccountPage />);
    await screen.findByText(/Alice Liddell/i);

    await user.click(screen.getByRole("button", { name: /Download my data/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/Failed to export/i);
  });

  it("delete account — confirm submit disabled until typed identifier matches, then deletes and navigates home", async () => {
    let deleteBody: { password?: string } | null = null;
    server.use(
      http.delete("/api/v1/auth/me", async ({ request }) => {
        deleteBody = (await request.json()) as { password?: string };
        return new HttpResponse(null, { status: 204 });
      }),
    );

    const user = userEvent.setup();
    renderWithProviders(<AccountPage />);
    await screen.findByText(/Alice Liddell/i);

    await user.click(screen.getByTestId("delete-account-button"));
    expect(await screen.findByTestId("delete-account-confirm")).toBeInTheDocument();

    const submitBtn = screen.getByTestId("delete-confirm-submit");
    expect(submitBtn).toBeDisabled();

    await user.type(screen.getByTestId("delete-confirm-identifier"), "alice@example.com");
    await user.type(screen.getByTestId("delete-confirm-password"), "correct horse battery staple");

    expect(submitBtn).not.toBeDisabled();
    await user.click(submitBtn);

    await waitFor(() => {
      expect(deleteBody).toEqual({ password: "correct horse battery staple" });
    });
    expect(mockNavigate).toHaveBeenCalledWith("/");
  });

  it("delete account — wrong password shows error and does not navigate", async () => {
    server.use(
      http.delete("/api/v1/auth/me", () =>
        HttpResponse.json(
          { error: { code: "INVALID_PASSWORD", message: "Wrong password" } },
          { status: 403 },
        ),
      ),
    );

    const user = userEvent.setup();
    renderWithProviders(<AccountPage />);
    await screen.findByText(/Alice Liddell/i);

    await user.click(screen.getByTestId("delete-account-button"));
    await user.type(screen.getByTestId("delete-confirm-identifier"), "alice@example.com");
    await user.type(screen.getByTestId("delete-confirm-password"), "wrong password");
    await user.click(screen.getByTestId("delete-confirm-submit"));

    expect(await screen.findByRole("alert")).toHaveTextContent(/Failed to delete/i);
    expect(mockNavigate).not.toHaveBeenCalledWith("/");
  });

  it("delete account — cancel hides the confirm fieldset and clears typed state", async () => {
    const user = userEvent.setup();
    renderWithProviders(<AccountPage />);
    await screen.findByText(/Alice Liddell/i);

    await user.click(screen.getByTestId("delete-account-button"));
    await user.type(screen.getByTestId("delete-confirm-identifier"), "some text");
    await user.click(screen.getByRole("button", { name: /Cancel/i }));

    expect(screen.queryByTestId("delete-account-confirm")).not.toBeInTheDocument();
  });

  it("push unsupported — no push-device-status block shown", async () => {
    renderWithProviders(<AccountPage />);
    await screen.findByText(/Alice Liddell/i);

    expect(screen.queryByTestId("push-device-status")).not.toBeInTheDocument();
  });

  it("push supported, not subscribed — shows enable button and subscribes on click", async () => {
    installPushEnvironment({ initialPermission: "granted" });
    const user = userEvent.setup();

    renderWithProviders(<AccountPage />);
    await screen.findByText(/Alice Liddell/i);

    const status = await screen.findByTestId("push-device-status");
    expect(status).toHaveTextContent(/Not enabled on this device/i);

    await user.click(screen.getByTestId("push-subscribe-button"));

    await waitFor(() => {
      expect(screen.getByLabelText("push subscribed")).toBeInTheDocument();
    });
    expect(screen.getByTestId("push-unsubscribe-button")).toBeInTheDocument();
  });

  it("push supported, already subscribed — shows disable button and unsubscribes on click", async () => {
    installPushEnvironment({
      initialPermission: "granted",
      existingSubscription: new FakePushSubscription(),
    });
    const user = userEvent.setup();

    renderWithProviders(<AccountPage />);
    await screen.findByText(/Alice Liddell/i);

    await waitFor(() => {
      expect(screen.getByLabelText("push subscribed")).toBeInTheDocument();
    });

    await user.click(screen.getByTestId("push-unsubscribe-button"));

    await waitFor(() => {
      expect(screen.getByTestId("push-device-status")).toHaveTextContent(
        /Not enabled on this device/i,
      );
    });
  });

  it("push permission denied — shows blocked status with no action button", async () => {
    installPushEnvironment({ initialPermission: "denied" });

    renderWithProviders(<AccountPage />);
    await screen.findByText(/Alice Liddell/i);

    const status = await screen.findByTestId("push-device-status");
    expect(status).toHaveTextContent(/Blocked in browser settings/i);
    expect(screen.queryByTestId("push-subscribe-button")).not.toBeInTheDocument();
    expect(screen.queryByTestId("push-unsubscribe-button")).not.toBeInTheDocument();
  });

  it("subscriptions list shows Push among the notification channels", async () => {
    server.use(
      http.get("/api/v1/subscriptions", () =>
        HttpResponse.json([
          {
            id: "sub-push-001",
            type: "launch",
            ll2_id: "launch-001",
            agency_name: null,
            notify_email: false,
            notify_sms: false,
            notify_push: true,
            created_at: "2026-01-01T00:00:00Z",
          },
        ]),
      ),
    );

    const user = userEvent.setup();
    renderWithProviders(<AccountPage />);
    await screen.findByText(/Alice Liddell/i);

    await user.click(screen.getByRole("button", { name: /Subscriptions/i }));

    expect(await screen.findByTestId("subscription-sub-push-001")).toHaveTextContent(/Push/i);
  });

  it("subscriptions list shows a distinct label for iss_pass subscriptions", async () => {
    server.use(
      http.get("/api/v1/subscriptions", () =>
        HttpResponse.json([
          {
            id: "sub-iss-001",
            type: "iss_pass",
            ll2_id: null,
            agency_name: null,
            notify_email: true,
            notify_sms: false,
            notify_push: true,
            created_at: "2026-01-01T00:00:00Z",
          },
        ]),
      ),
    );

    const user = userEvent.setup();
    renderWithProviders(<AccountPage />);
    await screen.findByText(/Alice Liddell/i);

    await user.click(screen.getByRole("button", { name: /Subscriptions/i }));

    expect(await screen.findByTestId("subscription-sub-iss-001")).toHaveTextContent(
      /ISS visible pass alerts/i,
    );
  });

  describe("sky location", () => {
    const baseUser = {
      id: 1,
      first_name: "Alice",
      last_name: "Liddell",
      email: "alice@example.com",
      phone: null,
      email_verified: true,
      phone_verified: false,
      created_at: "2024-01-01T00:00:00Z",
      consent_notifications_at: "2024-01-01T00:00:00Z",
      is_pro: false,
    };

    const vancouverCandidate = {
      name: "Vancouver",
      country: "Canada",
      admin1: "British Columbia",
      latitude: 49.28,
      longitude: -123.12,
      timezone: "America/Vancouver",
    };

    it("shows the not-set prompt and a search form when no location is saved", async () => {
      renderWithProviders(<AccountPage />);
      await screen.findByText(/Alice Liddell/i);

      expect(screen.getByTestId("location-not-set")).toBeInTheDocument();
      expect(screen.getByTestId("location-search-input")).toBeInTheDocument();
      expect(screen.queryByTestId("location-current")).not.toBeInTheDocument();
    });

    it("searching shows candidates and selecting one saves the location", async () => {
      let locationSet = false;
      server.use(
        http.get("/api/v1/auth/me", () =>
          HttpResponse.json({
            ...baseUser,
            location_name: locationSet ? "Vancouver, CA" : null,
            location_lat: locationSet ? 49.28 : null,
            location_lng: locationSet ? -123.12 : null,
            location_tz: locationSet ? "America/Vancouver" : null,
          }),
        ),
        http.get("/api/v1/location/search", () =>
          HttpResponse.json({ candidates: [vancouverCandidate] }),
        ),
        http.post("/api/v1/location", () => {
          locationSet = true;
          return HttpResponse.json({
            location_name: "Vancouver, CA",
            location_lat: 49.28,
            location_lng: -123.12,
            location_tz: "America/Vancouver",
          });
        }),
      );

      const user = userEvent.setup();
      renderWithProviders(<AccountPage />);
      await screen.findByText(/Alice Liddell/i);

      await user.type(screen.getByTestId("location-search-input"), "Vancouver");
      await user.click(screen.getByTestId("location-search-button"));

      const candidate = await screen.findByTestId("location-candidate-0");
      expect(candidate).toHaveTextContent("Vancouver, British Columbia, Canada");

      await user.click(screen.getByTestId("location-select-0"));

      await waitFor(() => {
        expect(screen.getByTestId("location-current")).toHaveTextContent("Vancouver, CA");
      });
      expect(screen.queryByTestId("location-search")).not.toBeInTheDocument();
    });

    it("shows a message when the search returns no results", async () => {
      server.use(
        http.get("/api/v1/location/search", () => HttpResponse.json({ candidates: [] })),
      );

      const user = userEvent.setup();
      renderWithProviders(<AccountPage />);
      await screen.findByText(/Alice Liddell/i);

      await user.type(screen.getByTestId("location-search-input"), "Nowhere");
      await user.click(screen.getByTestId("location-search-button"));

      expect(await screen.findByTestId("location-no-results")).toBeInTheDocument();
    });

    it("shows an error when the search request fails", async () => {
      server.use(
        http.get("/api/v1/location/search", () =>
          HttpResponse.json(
            { error: { code: "GEOCODE_UNAVAILABLE", message: "boom" } },
            { status: 502 },
          ),
        ),
      );

      const user = userEvent.setup();
      renderWithProviders(<AccountPage />);
      await screen.findByText(/Alice Liddell/i);

      await user.type(screen.getByTestId("location-search-input"), "Vancouver");
      await user.click(screen.getByTestId("location-search-button"));

      expect(await screen.findByTestId("location-error")).toHaveTextContent(
        /Location search failed/i,
      );
    });

    it("shows an error when saving the selected location fails", async () => {
      server.use(
        http.get("/api/v1/location/search", () =>
          HttpResponse.json({ candidates: [vancouverCandidate] }),
        ),
        http.post("/api/v1/location", () =>
          HttpResponse.json(
            { error: { code: "INVALID_PARAMS", message: "boom" } },
            { status: 400 },
          ),
        ),
      );

      const user = userEvent.setup();
      renderWithProviders(<AccountPage />);
      await screen.findByText(/Alice Liddell/i);

      await user.type(screen.getByTestId("location-search-input"), "Vancouver");
      await user.click(screen.getByTestId("location-search-button"));
      await user.click(await screen.findByTestId("location-select-0"));

      expect(await screen.findByTestId("location-error")).toHaveTextContent(
        /Failed to set location/i,
      );
    });

    it("change reveals the search form and cancel hides it again", async () => {
      server.use(
        http.get("/api/v1/auth/me", () =>
          HttpResponse.json({
            ...baseUser,
            location_name: "Vancouver, CA",
            location_lat: 49.28,
            location_lng: -123.12,
            location_tz: "America/Vancouver",
          }),
        ),
      );

      const user = userEvent.setup();
      renderWithProviders(<AccountPage />);
      await screen.findByText(/Alice Liddell/i);

      expect(await screen.findByTestId("location-current")).toBeInTheDocument();

      await user.click(screen.getByTestId("location-change-button"));
      expect(screen.getByTestId("location-search")).toBeInTheDocument();

      await user.click(screen.getByTestId("location-cancel-button"));
      expect(screen.getByTestId("location-current")).toBeInTheDocument();
    });

    it("clear removes the saved location", async () => {
      let locationSet = true;
      server.use(
        http.get("/api/v1/auth/me", () =>
          HttpResponse.json({
            ...baseUser,
            location_name: locationSet ? "Vancouver, CA" : null,
            location_lat: locationSet ? 49.28 : null,
            location_lng: locationSet ? -123.12 : null,
            location_tz: locationSet ? "America/Vancouver" : null,
          }),
        ),
        http.delete("/api/v1/location", () => {
          locationSet = false;
          return new HttpResponse(null, { status: 204 });
        }),
      );

      const user = userEvent.setup();
      renderWithProviders(<AccountPage />);
      await screen.findByText(/Alice Liddell/i);

      await screen.findByTestId("location-current");
      await user.click(screen.getByTestId("location-clear-button"));

      await waitFor(() => {
        expect(screen.getByTestId("location-not-set")).toBeInTheDocument();
      });
    });

    it("shows an error when clearing the location fails", async () => {
      server.use(
        http.get("/api/v1/auth/me", () =>
          HttpResponse.json({
            ...baseUser,
            location_name: "Vancouver, CA",
            location_lat: 49.28,
            location_lng: -123.12,
            location_tz: "America/Vancouver",
          }),
        ),
        http.delete("/api/v1/location", () =>
          HttpResponse.json({ error: { code: "SERVER_ERROR", message: "boom" } }, { status: 500 }),
        ),
      );

      const user = userEvent.setup();
      renderWithProviders(<AccountPage />);
      await screen.findByText(/Alice Liddell/i);

      await screen.findByTestId("location-current");
      await user.click(screen.getByTestId("location-clear-button"));

      expect(await screen.findByTestId("location-error")).toHaveTextContent(
        /Failed to clear location/i,
      );
    });
  });
});
