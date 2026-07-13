import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useDeleteAccount, useExportAccount, useMe, useSetConsent } from "@/hooks/useAuth";
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
  const setConsent = useSetConsent();
  const deleteAccount = useDeleteAccount();
  const exportAccount = useExportAccount();
  const [activeTab, setActiveTab] = useState<Tab>("profile");
  const [resendStatus, setResendStatus] = useState<Record<string, "sent" | "failed">>({});
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [deleteConfirmText, setDeleteConfirmText] = useState("");
  const [deletePassword, setDeletePassword] = useState("");
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [exportError, setExportError] = useState<string | null>(null);

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
      setResendStatus((prev) => ({ ...prev, [channel]: "sent" }));
    } catch {
      setResendStatus((prev) => ({ ...prev, [channel]: "failed" }));
    }
  }

  const deleteConfirmIdentifier = user.email ?? user.phone ?? "";

  async function handleExport() {
    setExportError(null);
    try {
      const data = await exportAccount.mutateAsync();
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "space-adventures-data-export.json";
      a.click();
      URL.revokeObjectURL(url);
    } catch {
      setExportError(t("account.exportFailed"));
    }
  }

  async function handleDeleteAccount() {
    setDeleteError(null);
    if (deleteConfirmText !== deleteConfirmIdentifier) return;
    try {
      await deleteAccount.mutateAsync(deletePassword);
      navigate("/");
    } catch {
      setDeleteError(t("account.deleteFailed"));
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
                  {resendStatus.email && (
                    <span>
                      {resendStatus.email === "sent" ? t("account.otpSent") : t("account.otpSendFailed")}
                    </span>
                  )}
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
                  {resendStatus.phone && (
                    <span>
                      {resendStatus.phone === "sent" ? t("account.otpSent") : t("account.otpSendFailed")}
                    </span>
                  )}
                </>
              )}
            </p>
          )}
          <p>
            <strong>{t("account.memberSince")}:</strong>{" "}
            {formatDate(user.created_at)}
          </p>
          <p>
            <label>
              <input
                type="checkbox"
                checked={!!user.consent_notifications_at}
                onChange={(e) => setConsent.mutate(e.target.checked)}
                disabled={setConsent.isPending}
                data-testid="consent-toggle"
              />
              {" "}{t("auth.consentNotifications")}
            </label>
          </p>

          <div className="account-danger-zone">
            <h2>{t("account.dangerZone")}</h2>

            <p>
              <button type="button" onClick={handleExport} disabled={exportAccount.isPending}>
                {t("account.downloadData")}
              </button>
              {exportError && <span role="alert">{exportError}</span>}
            </p>

            {!showDeleteConfirm ? (
              <button
                type="button"
                data-testid="delete-account-button"
                onClick={() => setShowDeleteConfirm(true)}
              >
                {t("account.deleteAccount")}
              </button>
            ) : (
              <fieldset data-testid="delete-account-confirm">
                <legend>{t("account.deleteAccount")}</legend>
                <p>{t("account.deleteAccountWarning")}</p>
                <label htmlFor="delete_confirm_identifier">
                  {t("account.deleteAccountConfirmLabel", { identifier: deleteConfirmIdentifier })}
                  <input
                    id="delete_confirm_identifier"
                    type="text"
                    value={deleteConfirmText}
                    onChange={(e) => setDeleteConfirmText(e.target.value)}
                    data-testid="delete-confirm-identifier"
                  />
                </label>
                <label htmlFor="delete_confirm_password">
                  {t("account.deleteAccountPasswordLabel")}
                  <input
                    id="delete_confirm_password"
                    type="password"
                    value={deletePassword}
                    onChange={(e) => setDeletePassword(e.target.value)}
                    data-testid="delete-confirm-password"
                  />
                </label>
                {deleteError && <span role="alert">{deleteError}</span>}
                <div>
                  <button
                    type="button"
                    data-testid="delete-confirm-submit"
                    onClick={handleDeleteAccount}
                    disabled={
                      deleteAccount.isPending || deleteConfirmText !== deleteConfirmIdentifier
                    }
                  >
                    {t("account.deleteAccountConfirmButton")}
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      setShowDeleteConfirm(false);
                      setDeleteConfirmText("");
                      setDeletePassword("");
                      setDeleteError(null);
                    }}
                  >
                    {t("account.deleteAccountCancel")}
                  </button>
                </div>
              </fieldset>
            )}
          </div>
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
                      ? t("account.subLaunchLabel", { id: sub.ll2_id ?? "—" })
                      : t("account.subAgencyLabel", { name: sub.agency_name ?? "—" })}
                  </strong>{" "}
                  <span>
                    {[
                      sub.notify_email && t("account.channelEmail"),
                      sub.notify_sms && t("account.channelSms"),
                    ]
                      .filter(Boolean)
                      .join(", ") || t("account.noChannels")}
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
