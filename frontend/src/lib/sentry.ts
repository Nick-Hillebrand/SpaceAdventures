// Lazily imports the Sentry browser SDK only when VITE_SENTRY_DSN is set, so
// unconfigured builds never pay for the bundle weight
// (17-worker-and-scheduling.md P3.6).
export function initSentry(): void {
  const dsn = import.meta.env.VITE_SENTRY_DSN as string | undefined;
  if (!dsn) {
    return;
  }
  void import("@sentry/react").then(({ init }) => {
    init({ dsn, tracesSampleRate: 0.05 });
  });
}
