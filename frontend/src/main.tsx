import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./index.css";
import "./i18n";
import App from "./App";
import { initSentry } from "./lib/sentry";

initSentry();

// The custom push-handling service worker (src/sw.ts) is only registered in
// production builds — in dev/test it would fight the MSW mock worker for
// the same scope (19-notification-channels-v2.md B1.2).
if (import.meta.env.PROD) {
  import("virtual:pwa-register").then(({ registerSW }) => registerSW({ immediate: true }));
}

const container = document.getElementById("root");
if (container) {
  createRoot(container).render(
    <StrictMode>
      <App />
    </StrictMode>,
  );
}
