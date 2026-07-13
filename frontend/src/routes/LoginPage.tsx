import { useState } from "react";
import { Link, useNavigate, useLocation } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { apiPost, setAccessToken } from "@/lib/api";
import type { TokenResponse } from "@/types/api";
import type { ApiError } from "@/lib/api";

export function safeReturnUrl(search: string): string {
  const raw = decodeURIComponent(new URLSearchParams(search).get("return") ?? "/");
  if (!raw.startsWith("/") || raw.startsWith("//") || raw.includes("://")) return "/";
  return raw;
}

function EyeIcon({ open }: { open: boolean }) {
  return open ? (
    <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
      <path d="M12 4.5C7 4.5 2.73 7.61 1 12c1.73 4.39 6 7.5 11 7.5s9.27-3.11 11-7.5c-1.73-4.39-6-7.5-11-7.5zM12 17c-2.76 0-5-2.24-5-5s2.24-5 5-5 5 2.24 5 5-2.24 5-5 5zm0-8c-1.66 0-3 1.34-3 3s1.34 3 3 3 3-1.34 3-3-1.34-3-3-3z"/>
    </svg>
  ) : (
    <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
      <path d="M12 7c2.76 0 5 2.24 5 5 0 .65-.13 1.26-.36 1.83l2.92 2.92c1.51-1.26 2.7-2.89 3.43-4.75-1.73-4.39-6-7.5-11-7.5-1.4 0-2.74.25-3.98.7l2.16 2.16C10.74 7.13 11.35 7 12 7zM2 4.27l2.28 2.28.46.46C3.08 8.3 1.78 10.02 1 12c1.73 4.39 6 7.5 11 7.5 1.55 0 3.03-.3 4.38-.84l.42.42L19.73 22 21 20.73 3.27 3 2 4.27zM7.53 9.8l1.55 1.55c-.05.21-.08.43-.08.65 0 1.66 1.34 3 3 3 .22 0 .44-.03.65-.08l1.55 1.55c-.67.33-1.41.53-2.2.53-2.76 0-5-2.24-5-5 0-.79.2-1.53.53-2.2zm4.31-.78l3.15 3.15.02-.16c0-1.66-1.34-3-3-3l-.17.01z"/>
    </svg>
  );
}

export default function LoginPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const { t } = useTranslation();
  const [emailOrPhone, setEmailOrPhone] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
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
      navigate(safeReturnUrl(location.search));
    } catch (err) {
      setError(err as ApiError);
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <div className="auth-layout">
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
          <div className="password-wrapper">
            <input
              id="password"
              type={showPassword ? "text" : "password"}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
            />
            <button
              type="button"
              className="password-toggle-btn"
              onClick={() => setShowPassword((v) => !v)}
              aria-label={showPassword ? t("auth.hidePassword") : t("auth.showPassword")}
              tabIndex={-1}
            >
              <EyeIcon open={showPassword} />
            </button>
          </div>
        </label>
        <button type="submit" disabled={isLoading}>
          {isLoading ? t("auth.loggingIn") : t("auth.loginTitle")}
        </button>
      </form>
      <p>
        {t("auth.noAccount")} <Link to="/register">{t("auth.register")}</Link>
      </p>
    </div>
    </div>
  );
}
