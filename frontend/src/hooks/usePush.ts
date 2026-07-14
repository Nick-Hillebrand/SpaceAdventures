import { useCallback, useEffect, useRef, useState } from "react";
import { apiDelete, apiGet, apiPost } from "@/lib/api";
import type { PushSubscribeRequest, VapidPublicKeyResponse } from "@/types/api";

export type PushPermissionState = "unsupported" | "default" | "granted" | "denied";

function isPushSupported(): boolean {
  return (
    typeof window !== "undefined" &&
    "serviceWorker" in navigator &&
    "PushManager" in window &&
    "Notification" in window
  );
}

// Web Push VAPID keys are URL-safe base64; `PushManager.subscribe` needs a
// raw Uint8Array applicationServerKey.
function urlBase64ToUint8Array(base64: string): Uint8Array {
  const padding = "=".repeat((4 - (base64.length % 4)) % 4);
  const normalized = (base64 + padding).replace(/-/g, "+").replace(/_/g, "/");
  const raw = atob(normalized);
  const output = new Uint8Array(raw.length);
  for (let i = 0; i < raw.length; i++) {
    output[i] = raw.charCodeAt(i);
  }
  return output;
}

function subscriptionToRequest(subscription: PushSubscription): PushSubscribeRequest {
  const json = subscription.toJSON();
  return {
    endpoint: json.endpoint ?? subscription.endpoint,
    keys: {
      p256dh: json.keys?.p256dh ?? "",
      auth: json.keys?.auth ?? "",
    },
  };
}

/**
 * Permission state machine + subscribe/unsubscribe flow for the Web Push
 * channel (19-notification-channels-v2.md B1.2). Never requests permission
 * on mount — only `subscribe()`, called from an explicit user action, may
 * trigger the browser's permission prompt (browser vendors punish
 * unsolicited prompts).
 */
export function usePush() {
  const [permission, setPermission] = useState<PushPermissionState>(() =>
    isPushSupported() ? (Notification.permission as PushPermissionState) : "unsupported",
  );
  const [isSubscribed, setIsSubscribed] = useState(false);
  const [isPending, setIsPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const supported = permission !== "unsupported";
  // Guards the mount-time subscription check against a race with an
  // explicit subscribe()/unsubscribe() call that starts (and finishes)
  // before the mount check's own async chain resolves — without this, the
  // stale mount-check result can land after and clobber the fresher one.
  const interacted = useRef(false);

  useEffect(() => {
    if (!supported) return;
    let cancelled = false;
    navigator.serviceWorker.ready
      .then((registration) => registration.pushManager.getSubscription())
      .then((subscription) => {
        if (!cancelled && !interacted.current) setIsSubscribed(subscription !== null);
      })
      .catch(() => {
        /* no active service worker registration yet — treat as unsubscribed */
      });
    return () => {
      cancelled = true;
    };
  }, [supported]);

  // Returns whether the subscription actually succeeded — callers must not
  // rely on reading `isSubscribed` right after `await`ing this, since a
  // state setter's effect isn't visible in the awaiting closure until the
  // next render.
  const subscribe = useCallback(async (): Promise<boolean> => {
    if (!supported) return false;
    interacted.current = true;
    setIsPending(true);
    setError(null);
    try {
      const requested = await Notification.requestPermission();
      setPermission(requested as PushPermissionState);
      if (requested !== "granted") return false;

      const registration = await navigator.serviceWorker.ready;
      const { public_key } = await apiGet<VapidPublicKeyResponse>(
        "/api/v1/push/vapid-public-key",
      );
      const subscription = await registration.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: urlBase64ToUint8Array(public_key),
      });
      await apiPost("/api/v1/push/subscribe", subscriptionToRequest(subscription));
      setIsSubscribed(true);
      return true;
    } catch {
      setError("push-subscribe-failed");
      return false;
    } finally {
      setIsPending(false);
    }
  }, [supported]);

  const unsubscribe = useCallback(async (): Promise<boolean> => {
    if (!supported) return false;
    interacted.current = true;
    setIsPending(true);
    setError(null);
    try {
      const registration = await navigator.serviceWorker.ready;
      const subscription = await registration.pushManager.getSubscription();
      if (subscription) {
        await apiDelete("/api/v1/push/subscribe", { endpoint: subscription.endpoint });
        await subscription.unsubscribe();
      }
      setIsSubscribed(false);
      return true;
    } catch {
      setError("push-unsubscribe-failed");
      return false;
    } finally {
      setIsPending(false);
    }
  }, [supported]);

  return { permission, isSubscribed, isPending, error, subscribe, unsubscribe };
}
