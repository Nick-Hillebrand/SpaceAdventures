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
  consent_notifications_at: "2024-01-01T00:00:00Z",
  is_pro: false,
  location_name: null,
  location_lat: null,
  location_lng: null,
  location_tz: null,
};

export const handlers = [
  http.get("/api/v1/health", () => HttpResponse.json({ status: "ok" })),

  http.post("/api/v1/auth/register", () =>
    HttpResponse.json({ id: 1, message: "Registration successful. Please check your OTP(s)." }, { status: 201 }),
  ),

  http.post("/api/v1/auth/login", () => HttpResponse.json({ access_token: "test-access-token" })),

  http.post("/api/v1/auth/refresh", () => HttpResponse.json({ access_token: "new-access-token" })),

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
        notify_push: false,
        created_at: "2026-01-01T00:00:00Z",
      },
      { status: 201 },
    ),
  ),

  http.delete("/api/v1/subscriptions/:id", () => new HttpResponse(null, { status: 204 })),

  // Realistic-shaped (87-char, unpadded-base64url) VAPID key — a real key is
  // a 65-byte uncompressed EC point, so an arbitrary shorter string would
  // fail `atob()`'s padding requirements in usePush's decode step.
  http.get("/api/v1/push/vapid-public-key", () =>
    HttpResponse.json({ public_key: "A".repeat(87) }),
  ),

  http.post("/api/v1/push/subscribe", () => new HttpResponse(null, { status: 204 })),

  http.delete("/api/v1/push/subscribe", () => new HttpResponse(null, { status: 204 })),

  http.get("/api/v1/settings", () =>
    HttpResponse.json({ nasa_key_set: false, n2yo_key_set: false }),
  ),

  http.get("/api/v1/location/search", () => HttpResponse.json({ candidates: [] })),

  http.post("/api/v1/location", () =>
    HttpResponse.json({
      location_name: "Vancouver, CA",
      location_lat: 49.28,
      location_lng: -123.12,
      location_tz: "America/Vancouver",
    }),
  ),

  http.delete("/api/v1/location", () => new HttpResponse(null, { status: 204 })),

  http.get("/api/v1/iss/passes", () =>
    HttpResponse.json({
      passes: [],
      fetched_at: "2026-01-01T00:00:00Z",
      cached: false,
      quota_exhausted: false,
    }),
  ),
];
