import { useState } from "react";
import { Link, useNavigate, useLocation } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { apiPost, setAccessToken, setRefreshToken } from "@/lib/api";
import type { TokenResponse } from "@/types/api";
import type { ApiError } from "@/lib/api";

export function safeReturnUrl(search: string): string {
  const raw = decodeURIComponent(new URLSearchParams(search).get("return") ?? "/");
  if (!raw.startsWith("/") || raw.startsWith("//") || raw.includes("://")) return "/";
  return raw;
}

export default function LoginPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const { t } = useTranslation();
  const [emailOrPhone, setEmailOrPhone] = useState("");
  const [password, setPassword] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setIsLoading(true);
    setError(null);
    try {
      const data = await apiPost<TokenResponse>("/api/v1/auth/login", {
        email_or_phone: emailOrPhone,
        password,
      });
      setAccessToken(data.access_token);
      setRefreshToken(data.refresh_token);
      navigate(safeReturnUrl(location.search));
    } catch (err) {
      setError(err as ApiError);
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <div className="login-page">
      <h1>{t("auth.loginTitle")}</h1>
      {error && (
        <div role="alert" className="error-banner">
          {error.message || t("auth.loginFailed")}
        </div>
      )}
      <form onSubmit={handleSubmit}>
        <label htmlFor="email_or_phone">
          {t("auth.emailOrPhoneLabel")}
          <input
            id="email_or_phone"
            type="text"
            value={emailOrPhone}
            onChange={(e) => setEmailOrPhone(e.target.value)}
            required
          />
        </label>
        <label htmlFor="password">
          {t("auth.password")}
          <input
            id="password"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
          />
        </label>
        <button type="submit" disabled={isLoading}>
          {isLoading ? t("auth.loggingIn") : t("auth.loginTitle")}
        </button>
      </form>
      <p>
        {t("auth.noAccount")} <Link to="/register">{t("auth.register")}</Link>
      </p>
    </div>
  );
}
