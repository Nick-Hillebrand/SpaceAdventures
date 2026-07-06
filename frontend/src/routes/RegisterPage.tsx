import { useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { apiPost } from "@/lib/api";
import type { ApiError } from "@/lib/api";

type Step = "register" | "otp";

export default function RegisterPage() {
  const { t } = useTranslation();
  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [email, setEmail] = useState("");
  const [phone, setPhone] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [step, setStep] = useState<Step>("register");
  const [userId, setUserId] = useState<number | null>(null);
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
      });
      setUserId(data.id);

      const tokenData = await apiPost<{ access_token: string; refresh_token: string }>(
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
          <input
            id="password"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
          />
        </label>
        <label htmlFor="confirm_password">
          {t("auth.confirmPassword")}
          <input
            id="confirm_password"
            type="password"
            value={confirmPassword}
            onChange={(e) => setConfirmPassword(e.target.value)}
            required
          />
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
