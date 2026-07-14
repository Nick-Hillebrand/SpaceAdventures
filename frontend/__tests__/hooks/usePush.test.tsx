import { act, renderHook, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it, vi } from "vitest";
import { usePush } from "@/hooks/usePush";
import { server } from "@/msw/server";

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

  return { requestPermission, subscribe, getSubscription, registration };
}

describe("usePush", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    // @ts-expect-error — cleaning up the test-only navigator override
    delete navigator.serviceWorker;
  });

  it("reports 'unsupported' when the browser has no Push API and never touches Notification", async () => {
    const { result } = renderHook(() => usePush());
    expect(result.current.permission).toBe("unsupported");
    expect(result.current.isSubscribed).toBe(false);

    await act(async () => {
      await result.current.subscribe();
    });
    // no-op: still unsupported, no crash
    expect(result.current.permission).toBe("unsupported");
  });

  it("does not call Notification.requestPermission on mount (no auto-prompt)", async () => {
    const { requestPermission } = installPushEnvironment({ initialPermission: "default" });

    renderHook(() => usePush());

    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(requestPermission).not.toHaveBeenCalled();
  });

  it("reflects an existing subscription found on mount", async () => {
    installPushEnvironment({
      initialPermission: "granted",
      existingSubscription: new FakePushSubscription(),
    });

    const { result } = renderHook(() => usePush());

    await waitFor(() => expect(result.current.isSubscribed).toBe(true));
  });

  it("subscribe() requests permission, fetches VAPID key, subscribes, and POSTs the subscription", async () => {
    const { requestPermission, subscribe } = installPushEnvironment({
      initialPermission: "granted",
    });
    let postBody: unknown = null;
    server.use(
      http.post("/api/v1/push/subscribe", async ({ request }) => {
        postBody = await request.json();
        return new HttpResponse(null, { status: 204 });
      }),
    );

    const { result } = renderHook(() => usePush());

    await act(async () => {
      await result.current.subscribe();
    });

    expect(requestPermission).toHaveBeenCalledTimes(1);
    expect(subscribe).toHaveBeenCalledTimes(1);
    expect(subscribe.mock.calls[0][0]).toMatchObject({ userVisibleOnly: true });
    await waitFor(() => expect(result.current.isSubscribed).toBe(true));
    expect(postBody).toMatchObject({
      endpoint: "https://push.example/endpoint-1",
      keys: { p256dh: "test-p256dh", auth: "test-auth" },
    });
  });

  it("subscribe() when permission is denied does not call pushManager.subscribe", async () => {
    const { subscribe } = installPushEnvironment({ initialPermission: "denied" });

    const { result } = renderHook(() => usePush());

    await act(async () => {
      await result.current.subscribe();
    });

    expect(subscribe).not.toHaveBeenCalled();
    expect(result.current.permission).toBe("denied");
    expect(result.current.isSubscribed).toBe(false);
  });

  it("unsubscribe() deletes the backend row and calls subscription.unsubscribe()", async () => {
    const existing = new FakePushSubscription();
    installPushEnvironment({ initialPermission: "granted", existingSubscription: existing });
    let deleteBody: unknown = null;
    server.use(
      http.delete("/api/v1/push/subscribe", async ({ request }) => {
        deleteBody = await request.json();
        return new HttpResponse(null, { status: 204 });
      }),
    );

    const { result } = renderHook(() => usePush());
    await waitFor(() => expect(result.current.isSubscribed).toBe(true));

    await act(async () => {
      await result.current.unsubscribe();
    });

    expect(existing.unsubscribe).toHaveBeenCalledTimes(1);
    expect(deleteBody).toMatchObject({ endpoint: "https://push.example/endpoint-1" });
    expect(result.current.isSubscribed).toBe(false);
  });
});
