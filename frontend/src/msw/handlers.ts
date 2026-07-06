import { http, HttpResponse } from "msw";

const mockUser = {
  id: 1,
  first_name: "Alice",
  last_name: "Liddell",
  email: "alice@example.com",
  phone: null,
  email_verified: true,
  phone_verified: false,
  created_at: "2024-01-01T00:00:00Z",
};

export const handlers = [
  http.get("/api/v1/health", () => HttpResponse.json({ status: "ok" })),

  http.post("/api/v1/auth/register", () =>
    HttpResponse.json({ id: 1, message: "Registration successful. Please check your OTP(s)." }, { status: 201 }),
  ),

  http.post("/api/v1/auth/login", () =>
    HttpResponse.json({ access_token: "test-access-token", refresh_token: "test-refresh-token" }),
  ),

  http.post("/api/v1/auth/refresh", () =>
    HttpResponse.json({ access_token: "new-access-token", refresh_token: "new-refresh-token" }),
  ),

  http.post("/api/v1/auth/logout", () => HttpResponse.json({ message: "Logged out" })),

  http.get("/api/v1/auth/me", () => HttpResponse.json(mockUser)),

  http.post("/api/v1/auth/verify/email", () => HttpResponse.json({ message: "Email verified" })),
  http.post("/api/v1/auth/verify/phone", () => HttpResponse.json({ message: "Phone verified" })),
  http.post("/api/v1/auth/verify/resend", () => HttpResponse.json({ message: "OTP resent" })),

  http.get("/api/v1/subscriptions", () => HttpResponse.json([])),

  http.post("/api/v1/subscriptions/unsubscribe", () =>
    HttpResponse.json({ message: "Unsubscribed successfully" }),
  ),

  http.post("/api/v1/subscriptions", () =>
    HttpResponse.json(
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
    ),
  ),

  http.delete("/api/v1/subscriptions/:id", () => new HttpResponse(null, { status: 204 })),

  http.get("/api/v1/settings", () =>
    HttpResponse.json({ nasa_key_set: false, n2yo_key_set: false }),
  ),

  http.post("/api/v1/settings/nasa-api-key", () =>
    HttpResponse.json({ message: "NASA API key updated" }),
  ),

  http.post("/api/v1/settings/n2yo-api-key", () =>
    HttpResponse.json({ message: "N2YO API key updated" }),
  ),
];
