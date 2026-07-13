import { afterEach, describe, expect, it, vi } from "vitest";

describe("initSentry", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
    vi.resetModules();
    vi.doUnmock("@sentry/react");
  });

  it("does not import the Sentry SDK when VITE_SENTRY_DSN is unset", async () => {
    vi.stubEnv("VITE_SENTRY_DSN", "");
    const sentryInit = vi.fn();
    vi.doMock("@sentry/react", () => ({ init: sentryInit }));

    const { initSentry } = await import("./sentry");
    initSentry();
    await Promise.resolve();

    expect(sentryInit).not.toHaveBeenCalled();
  });

  it("initializes the Sentry SDK when VITE_SENTRY_DSN is set", async () => {
    vi.stubEnv("VITE_SENTRY_DSN", "https://examplePublicKey@o0.ingest.sentry.io/0");
    const sentryInit = vi.fn();
    vi.doMock("@sentry/react", () => ({ init: sentryInit }));

    const { initSentry } = await import("./sentry");
    initSentry();
    await vi.waitFor(() => expect(sentryInit).toHaveBeenCalled());

    expect(sentryInit).toHaveBeenCalledWith({
      dsn: "https://examplePublicKey@o0.ingest.sentry.io/0",
      tracesSampleRate: 0.05,
    });
  });
});
