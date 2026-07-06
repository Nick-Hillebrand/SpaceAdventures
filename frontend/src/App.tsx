import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
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

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: false },
  },
});

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Navbar />
        <ErrorBoundary>
        <Routes>
          <Route path="/apod" element={<ApodPage />} />
          <Route path="/iss" element={<IssPage />} />
          <Route path="/launches" element={<LaunchesPage />} />
          <Route path="/mars" element={<MarsPage />} />
          <Route path="/neo" element={<NeoPage />} />
          <Route path="/space-weather" element={<SpaceWeatherPage />} />
          <Route path="/login" element={<LoginPage />} />
          <Route path="/register" element={<RegisterPage />} />
          <Route path="/account" element={<AccountPage />} />
          <Route path="/confirm-unsubscribe" element={<ConfirmUnsubscribePage />} />
          <Route path="/settings" element={<SettingsPage />} />
          <Route path="/" element={<Navigate to="/apod" replace />} />
        </Routes>
        </ErrorBoundary>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
