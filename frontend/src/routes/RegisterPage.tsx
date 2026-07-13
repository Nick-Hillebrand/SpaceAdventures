import { useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { apiPost } from "@/lib/api";
import type { ApiError } from "@/lib/api";

type Step = "register" | "otp";

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

export default function RegisterPage() {
  const { t } = useTranslation();
  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [email, setEmail] = useState("");
  const [phone, setPhone] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [consentNotifications, setConsentNotifications] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [step, setStep] = useState<Step>("register");
  const [, setUserId] = useState<number | null>(null);
  const [emailOtp, setEmailOtp] = useState("");
  const [phoneOtp, setPhoneOtp] = useState("");
  const [otpError, setOtpError] = useState<string | null>(null);
  const [accessToken, setAccessTokenLocal] = useState<string | null>(null);

  function validate(): string | null {
    if (!email && !phone) return t("auth.emailOrPhone");
    if (password.length < 8) return t("auth.passwordTooShort");
    if (password !== confirmPassword) return t("auth.passwordMismatch");
    return null;
  }

  async function handleRegister(e: React.FormEvent) {
    e.preventDefault();
    const validationError = validate();
    if (validationError) {
      setError(validationError);
      return;
    }
    setIsLoading(true);
    setError(null);
    try {
      const data = await apiPost<{ id: number }>("/api/v1/auth/register", {
        first_name: firstName,
        last_name: lastName,
        email: email || undefined,
        phone: phone || undefined,
        password,
        consent_notifications: consentNotifications,
      });
      setUserId(data.id);

      const tokenData = await apiPost<{ access_token: string }>(
        "/api/v1/auth/login",
        { email_or_phone: email || phone, password }
      );
      setAccessTokenLocal(tokenData.access_token);
      setStep("otp");
    } catch (err) {
      const apiErr = err as ApiError;
      setError(apiErr.message || t("common.error"));
    } finally {
      setIsLoading(false);
    }
  }

  async function handleOtpSubmit(channel: "email" | "phone", otp: string) {
    if (!accessToken) return;
    setOtpError(null);
    try {
      await apiPost(
        channel === "email" ? "/api/v1/auth/verify/email" : "/api/v1/auth/verify/phone",
        { otp },
        accessToken,
      );
    } catch (err) {
      const apiErr = err as ApiError;
      setOtpError(apiErr.message || t("common.error"));
    }
  }

  if (step === "otp") {
    return (
      <div className="auth-layout">
      <div className="register-page">
        <h1>{t("auth.verifyAccount")}</h1>
        {otpError && (
          <div role="alert" className="error-banner">
            {otpError}
          </div>
        )}
        {email && (
          <div>
            <h2>{t("auth.emailOtpSection")}</h2>
            <label htmlFor="email-otp">
              {t("auth.verifyEmail")}
              <input
                id="email-otp"
                type="text"
                value={emailOtp}
                onChange={(e) => setEmailOtp(e.target.value)}
              />
            </label>
            <button type="button" onClick={() => handleOtpSubmit("email", emailOtp)}>
              {t("auth.verifyEmailButton")}
            </button>
          </div>
        )}
        {phone && (
          <div>
            <h2>{t("auth.phoneOtpSection")}</h2>
            <label htmlFor="phone-otp">
              {t("auth.verifyPhone")}
              <input
                id="phone-otp"
                type="text"
                value={phoneOtp}
                onChange={(e) => setPhoneOtp(e.target.value)}
              />
            </label>
            <button type="button" onClick={() => handleOtpSubmit("phone", phoneOtp)}>
              {t("auth.verifyPhoneButton")}
            </button>
          </div>
        )}
      </div>
      </div>
    );
  }

  return (
    <div className="auth-layout">
    <div className="register-page">
      <h1>{t("auth.registerTitle")}</h1>
      {error && (
        <div role="alert" className="error-banner">
          {error}
        </div>
      )}
      <form onSubmit={handleRegister}>
        <label htmlFor="first_name">
          {t("auth.firstName")}
          <input
            id="first_name"
            type="text"
            value={firstName}
            onChange={(e) => setFirstName(e.target.value)}
            required
          />
        </label>
        <label htmlFor="last_name">
          {t("auth.lastName")}
          <input
            id="last_name"
            type="text"
            value={lastName}
            onChange={(e) => setLastName(e.target.value)}
            required
          />
        </label>
        <label htmlFor="email">
          {t("auth.emailOptional")}
          <input
            id="email"
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
        </label>
        <label htmlFor="phone">
          {t("auth.phoneOptional")}
          <input
            id="phone"
            type="tel"
            value={phone}
            onChange={(e) => setPhone(e.target.value)}
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
        <label htmlFor="confirm_password">
          {t("auth.confirmPassword")}
          <div className="password-wrapper">
            <input
              id="confirm_password"
              type={showConfirmPassword ? "text" : "password"}
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              required
            />
            <button
              type="button"
              className="password-toggle-btn"
              onClick={() => setShowConfirmPassword((v) => !v)}
              aria-label={showConfirmPassword ? t("auth.hidePassword") : t("auth.showPassword")}
              tabIndex={-1}
            >
              <EyeIcon open={showConfirmPassword} />
            </button>
          </div>
        </label>
        <label htmlFor="consent_notifications" className="consent-checkbox-label">
          <input
            id="consent_notifications"
            type="checkbox"
            checked={consentNotifications}
            onChange={(e) => setConsentNotifications(e.target.checked)}
          />
          {" "}{t("auth.consentNotifications")}
        </label>
        <button type="submit" disabled={isLoading}>
          {isLoading ? t("auth.creatingAccount") : t("auth.register")}
        </button>
      </form>
      <p>
        {t("auth.alreadyHaveAccount")} <Link to="/login">{t("auth.loginTitle")}</Link>
      </p>
    </div>
    </div>
  );
}
