/// <reference lib="webworker" />

// Custom service worker (19-notification-channels-v2.md B1.2), injected via
// vite-plugin-pwa's `injectManifest` strategy. Precaches the app shell only —
// API responses are never cached here (stale launch/APOD data is worse than
// no cache), so `self.__WB_MANIFEST` only ever contains build assets.
import { precacheAndRoute } from "workbox-precaching";

declare const self: ServiceWorkerGlobalScope;

precacheAndRoute(self.__WB_MANIFEST);

interface PushPayload {
  title: string;
  body: string;
  url?: string;
}

self.addEventListener("push", (event: PushEvent) => {
  let payload: PushPayload = { title: "Space Adventures", body: "" };
  if (event.data) {
    try {
      payload = { ...payload, ...event.data.json() };
    } catch {
      payload = { ...payload, body: event.data.text() };
    }
  }

  event.waitUntil(
    self.registration.showNotification(payload.title, {
      body: payload.body,
      data: { url: payload.url ?? "/" },
    }),
  );
});

self.addEventListener("notificationclick", (event: NotificationEvent) => {
  event.notification.close();
  const url = (event.notification.data as { url?: string } | undefined)?.url ?? "/";
  event.waitUntil(self.clients.openWindow(url));
});
