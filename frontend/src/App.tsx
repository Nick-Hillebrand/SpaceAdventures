import { lazy, Suspense } from "react";
import { BrowserRouter, Routes, Route, Navigate, useLocation } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import Navbar from "@/components/Navbar";
import ErrorBoundary from "@/components/ErrorBoundary";
import LoginPage from "@/routes/LoginPage";
import RegisterPage from "@/routes/RegisterPage";
import AccountPage from "@/routes/AccountPage";
import ConfirmUnsubscribePage from "@/routes/ConfirmUnsubscribePage";
import SettingsPage from "@/routes/SettingsPage";
import ApodPage from "@/routes/ApodPage";
import IssPage from "@/routes/IssPage";
import LaunchesPage from "@/routes/LaunchesPage";
import MarsPage from "@/routes/MarsPage";
import NeoPage from "@/routes/NeoPage";
import SpaceWeatherPage from "@/routes/SpaceWeatherPage";
import SolarSystemPage from "@/routes/SolarSystemPage";

// Mission replay routes pull in the three.js-backed scene engine; lazy-load
// their chunk so /apod et al. don't pay for it (26-performance.md bundle budget).
const MissionsIndexPage = lazy(() => import("@/routes/MissionsIndexPage"));
const MissionPage = lazy(() => import("@/routes/MissionPage"));

const EMBED_PATH = /^\/missions\/[^/]+\/embed\/?$/;

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: false },
  },
});

function AppShell() {
  const location = useLocation();
  // The embed route is chrome-less by design (Architecture/22 G3): no Navbar,
  // so it can be dropped into a same-origin iframe as a bare widget.
  const isEmbed = EMBED_PATH.test(location.pathname);

  return (
    <>
      {!isEmbed && <Navbar />}
      <ErrorBoundary>
        <Suspense fallback={null}>
          <Routes>
            <Route path="/apod" element={<ApodPage />} />
            <Route path="/iss" element={<IssPage />} />
            <Route path="/launches" element={<LaunchesPage />} />
            <Route path="/mars" element={<MarsPage />} />
            <Route path="/neo" element={<NeoPage />} />
            <Route path="/space-weather" element={<SpaceWeatherPage />} />
            <Route path="/solar-system" element={<SolarSystemPage />} />
            <Route path="/missions" element={<MissionsIndexPage />} />
            <Route path="/missions/:slug/embed" element={<MissionPage embed />} />
            <Route path="/missions/:slug" element={<MissionPage />} />
            <Route path="/login" element={<LoginPage />} />
            <Route path="/register" element={<RegisterPage />} />
            <Route path="/account" element={<AccountPage />} />
            <Route path="/confirm-unsubscribe" element={<ConfirmUnsubscribePage />} />
            <Route path="/settings" element={<SettingsPage />} />
            <Route path="/" element={<Navigate to="/apod" replace />} />
          </Routes>
        </Suspense>
      </ErrorBoundary>
    </>
  );
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <AppShell />
      </BrowserRouter>
    </QueryClientProvider>
  );
}
