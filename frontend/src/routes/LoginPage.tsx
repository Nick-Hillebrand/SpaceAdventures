import { useState } from "react";
import { Link, useNavigate, useLocation } from "react-router-dom";
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
      <h1>Log In</h1>
      {error && (
        <div role="alert" className="error-banner">
          {error.message || "Login failed. Please check your credentials."}
        </div>
      )}
      <form onSubmit={handleSubmit}>
        <label htmlFor="email_or_phone">
          Email or Phone
          <input
            id="email_or_phone"
            type="text"
            value={emailOrPhone}
            onChange={(e) => setEmailOrPhone(e.target.value)}
            required
          />
        </label>
        <label htmlFor="password">
          Password
          <input
            id="password"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
          />
        </label>
        <button type="submit" disabled={isLoading}>
          {isLoading ? "Logging in…" : "Log In"}
        </button>
      </form>
      <p>
        Don&apos;t have an account? <Link to="/register">Register</Link>
      </p>
    </div>
  );
}
