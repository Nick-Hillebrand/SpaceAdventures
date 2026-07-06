import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useMe } from "@/hooks/useAuth";
import { useSubscriptions, useDeleteSubscription } from "@/hooks/useSubscriptions";
import { apiPost } from "@/lib/api";
import { formatDate } from "@/lib/dateTime";

type Tab = "profile" | "subscriptions";

export default function AccountPage() {
  const navigate = useNavigate();
  const { t } = useTranslation();
  const { data: user, isLoading, isError, error } = useMe();
  const { data: subscriptions, isLoading: subsLoading } = useSubscriptions();
  const deleteSubscription = useDeleteSubscription();
  const [activeTab, setActiveTab] = useState<Tab>("profile");
  const [resendStatus, setResendStatus] = useState<Record<string, string>>({});

  if (isError && error && error.status === 401) {
    navigate("/login?return=/account");
    return null;
  }

  if (isLoading) {
    return <p role="status">{t("common.loading")}</p>;
  }

  if (!user) {
    return null;
  }

  async function handleResend(channel: "email" | "phone") {
    try {
      await apiPost("/api/v1/auth/verify/resend", { channel });
      setResendStatus((prev) => ({ ...prev, [channel]: "OTP sent!" }));
    } catch {
      setResendStatus((prev) => ({ ...prev, [channel]: "Failed to send OTP." }));
    }
  }

  return (
    <div className="account-page">
      <h1>{t("account.title")}</h1>
      <nav>
        <button
          type="button"
          onClick={() => setActiveTab("profile")}
          aria-selected={activeTab === "profile"}
        >
          {t("account.profileTab")}
        </button>
        <button
          type="button"
          onClick={() => setActiveTab("subscriptions")}
          aria-selected={activeTab === "subscriptions"}
        >
          {t("account.subscriptionsTab")}
        </button>
      </nav>

      {activeTab === "profile" && (
        <div>
          <p>
            <strong>{t("account.name")}:</strong> {user.first_name} {user.last_name}
          </p>
          {user.email && (
            <p>
              <strong>{t("account.email")}:</strong> {user.email}{" "}
              {user.email_verified ? (
                <span aria-label="email verified">✓ {t("account.verified")}</span>
              ) : (
                <>
                  <span>{t("account.unverified")}</span>
                  <button type="button" onClick={() => handleResend("email")}>
                    {t("account.resendOtp")}
                  </button>
                  {resendStatus.email && <span>{resendStatus.email}</span>}
                </>
              )}
            </p>
          )}
          {user.phone && (
            <p>
              <strong>{t("account.phone")}:</strong> {user.phone}{" "}
              {user.phone_verified ? (
                <span aria-label="phone verified">✓ {t("account.verified")}</span>
              ) : (
                <>
                  <span>{t("account.unverified")}</span>
                  <button type="button" onClick={() => handleResend("phone")}>
                    {t("account.resendOtp")}
                  </button>
                  {resendStatus.phone && <span>{resendStatus.phone}</span>}
                </>
              )}
            </p>
          )}
          <p>
            <strong>{t("account.memberSince")}:</strong>{" "}
            {formatDate(user.created_at)}
          </p>
        </div>
      )}

      {activeTab === "subscriptions" && (
        <div data-testid="subscriptions-tab">
          <h2>{t("account.subscriptionsTab")}</h2>
          {subsLoading ? (
            <p>{t("account.loadingSubscriptions")}</p>
          ) : !subscriptions || subscriptions.length === 0 ? (
            <p data-testid="no-subscriptions">{t("account.noSubscriptions")}</p>
          ) : (
            <ul data-testid="subscriptions-list">
              {subscriptions.map((sub) => (
                <li key={sub.id} data-testid={`subscription-${sub.id}`}>
                  <strong>
                    {sub.type === "launch"
                      ? `Launch: ${sub.ll2_id ?? "—"}`
                      : `Agency: ${sub.agency_name ?? "—"}`}
                  </strong>{" "}
                  <span>
                    {[
                      sub.notify_email && t("account.channelEmail"),
                      sub.notify_sms && t("account.channelSms"),
                    ]
                      .filter(Boolean)
                      .join(", ") || "No channels"}
                  </span>{" "}
                  <button
                    type="button"
                    data-testid={`delete-sub-${sub.id}`}
                    onClick={() => deleteSubscription.mutate(sub.id)}
                    disabled={deleteSubscription.isPending}
                  >
                    {t("account.unsubscribe")}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
