import { type FormEvent, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useDeleteAccount, useExportAccount, useMe, useSetConsent } from "@/hooks/useAuth";
import { useSubscriptions, useDeleteSubscription } from "@/hooks/useSubscriptions";
import { usePush } from "@/hooks/usePush";
import { useClearLocation, useSearchLocation, useSetLocation } from "@/hooks/useLocation";
import { useRotateIcalToken } from "@/hooks/useIcal";
import { apiPost } from "@/lib/api";
import { formatDate } from "@/lib/dateTime";
import type { LocationCandidate } from "@/types/api";

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
  const push = usePush();
  const searchLocation = useSearchLocation();
  const setLocation = useSetLocation();
  const clearLocation = useClearLocation();
  const [activeTab, setActiveTab] = useState<Tab>("profile");
  const [resendStatus, setResendStatus] = useState<Record<string, "sent" | "failed">>({});
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [deleteConfirmText, setDeleteConfirmText] = useState("");
  const [deletePassword, setDeletePassword] = useState("");
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [exportError, setExportError] = useState<string | null>(null);
  const [locationQuery, setLocationQuery] = useState("");
  const [editingLocation, setEditingLocation] = useState(false);
  const [locationError, setLocationError] = useState<string | null>(null);
  const rotateIcal = useRotateIcalToken();
  const [icalCopied, setIcalCopied] = useState(false);
  const [icalRotateConfirm, setIcalRotateConfirm] = useState(false);
  const [icalError, setIcalError] = useState<string | null>(null);

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

  function icalFeedUrl(token: string): string {
    return `webcal://${window.location.host}/api/v1/ical/${token}.ics`;
  }

  async function handleCopyIcalUrl() {
    if (!user.ical_token) return;
    try {
      await navigator.clipboard.writeText(icalFeedUrl(user.ical_token));
      setIcalCopied(true);
      setTimeout(() => setIcalCopied(false), 2000);
    } catch {
      // Clipboard unavailable — no-op (the URL is displayed inline).
    }
  }

  async function handleRotateIcal() {
    setIcalError(null);
    setIcalRotateConfirm(false);
    try {
      await rotateIcal.mutateAsync();
    } catch {
      setIcalError(t("account.icalRotateError"));
    }
  }

  async function handleLocationSearch(e: FormEvent) {
    e.preventDefault();
    setLocationError(null);
    try {
      await searchLocation.mutateAsync(locationQuery);
    } catch {
      setLocationError(t("account.locationSearchFailed"));
    }
  }

  async function handleSelectLocation(candidate: LocationCandidate) {
    setLocationError(null);
    try {
      await setLocation.mutateAsync({
        name: candidate.name,
        latitude: candidate.latitude,
        longitude: candidate.longitude,
        timezone: candidate.timezone,
      });
      setEditingLocation(false);
      setLocationQuery("");
      searchLocation.reset();
    } catch {
      setLocationError(t("account.locationSetFailed"));
    }
  }

  async function handleClearLocation() {
    setLocationError(null);
    try {
      await clearLocation.mutateAsync();
    } catch {
      setLocationError(t("account.locationClearFailed"));
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

          {push.permission !== "unsupported" && (
            <p data-testid="push-device-status">
              <strong>{t("account.pushDevice")}:</strong>{" "}
              {push.permission === "denied" ? (
                <span>{t("account.pushDenied")}</span>
              ) : push.isSubscribed ? (
                <>
                  <span aria-label="push subscribed">✓ {t("account.pushSubscribed")}</span>
                  <button
                    type="button"
                    onClick={() => push.unsubscribe()}
                    disabled={push.isPending}
                    data-testid="push-unsubscribe-button"
                  >
                    {t("account.pushDisable")}
                  </button>
                </>
              ) : (
                <>
                  <span>{t("account.pushNotSubscribed")}</span>
                  <button
                    type="button"
                    onClick={() => push.subscribe()}
                    disabled={push.isPending}
                    data-testid="push-subscribe-button"
                  >
                    {t("account.pushEnable")}
                  </button>
                </>
              )}
            </p>
          )}

          <div data-testid="location-section">
            <h2>{t("account.locationTitle")}</h2>
            {user.location_name && !editingLocation ? (
              <p data-testid="location-current">
                <strong>{t("account.locationCurrentLabel")}:</strong> {user.location_name}{" "}
                <button
                  type="button"
                  onClick={() => setEditingLocation(true)}
                  data-testid="location-change-button"
                >
                  {t("account.locationChange")}
                </button>{" "}
                <button
                  type="button"
                  onClick={handleClearLocation}
                  disabled={clearLocation.isPending}
                  data-testid="location-clear-button"
                >
                  {t("account.locationClear")}
                </button>
              </p>
            ) : (
              <div data-testid="location-search">
                {!user.location_name && (
                  <p data-testid="location-not-set">{t("account.locationNotSet")}</p>
                )}
                <form onSubmit={handleLocationSearch}>
                  <label htmlFor="location_search_input">
                    {t("account.locationSearchLabel")}
                    <input
                      id="location_search_input"
                      type="text"
                      value={locationQuery}
                      onChange={(e) => setLocationQuery(e.target.value)}
                      placeholder={t("account.locationSearchPlaceholder")}
                      data-testid="location-search-input"
                    />
                  </label>{" "}
                  <button
                    type="submit"
                    disabled={searchLocation.isPending || !locationQuery.trim()}
                    data-testid="location-search-button"
                  >
                    {searchLocation.isPending
                      ? t("account.locationSearching")
                      : t("account.locationSearchButton")}
                  </button>{" "}
                  {editingLocation && user.location_name && (
                    <button
                      type="button"
                      onClick={() => {
                        setEditingLocation(false);
                        setLocationQuery("");
                        searchLocation.reset();
                      }}
                      data-testid="location-cancel-button"
                    >
                      {t("account.deleteAccountCancel")}
                    </button>
                  )}
                </form>
                {searchLocation.data &&
                  (searchLocation.data.candidates.length === 0 ? (
                    <p data-testid="location-no-results">{t("account.locationNoResults")}</p>
                  ) : (
                    <ul data-testid="location-candidates-list">
                      {searchLocation.data.candidates.map((c, i) => (
                        <li key={`${c.latitude}-${c.longitude}-${i}`} data-testid={`location-candidate-${i}`}>
                          {[c.name, c.admin1, c.country].filter(Boolean).join(", ")}{" "}
                          <button
                            type="button"
                            onClick={() => handleSelectLocation(c)}
                            disabled={setLocation.isPending}
                            data-testid={`location-select-${i}`}
                          >
                            {t("account.locationUseThis")}
                          </button>
                        </li>
                      ))}
                    </ul>
                  ))}
              </div>
            )}
            {locationError && (
              <span role="alert" data-testid="location-error">
                {locationError}
              </span>
            )}
          </div>

          <div data-testid="ical-section">
            <h2>{t("account.icalTitle")}</h2>
            <p>{t("account.icalDescription")}</p>
            {!user.is_pro ? (
              <p data-testid="ical-pro-required">{t("account.icalProRequired")}</p>
            ) : user.ical_token ? (
              <>
                <p data-testid="ical-url" style={{ wordBreak: "break-all" }}>
                  {icalFeedUrl(user.ical_token)}
                </p>
                <button
                  type="button"
                  onClick={handleCopyIcalUrl}
                  data-testid="ical-copy-button"
                >
                  {icalCopied ? t("account.icalCopied") : t("account.icalCopyUrl")}
                </button>{" "}
                {!icalRotateConfirm ? (
                  <button
                    type="button"
                    onClick={() => setIcalRotateConfirm(true)}
                    data-testid="ical-rotate-button"
                  >
                    {t("account.icalRotate")}
                  </button>
                ) : (
                  <span data-testid="ical-rotate-confirm">
                    <strong>{t("account.icalRotateConfirmTitle")}</strong>{" "}
                    {t("account.icalRotateConfirmBody")}{" "}
                    <button
                      type="button"
                      onClick={handleRotateIcal}
                      disabled={rotateIcal.isPending}
                      data-testid="ical-rotate-confirm-button"
                    >
                      {t("account.icalRotateConfirm")}
                    </button>{" "}
                    <button
                      type="button"
                      onClick={() => setIcalRotateConfirm(false)}
                      data-testid="ical-rotate-cancel-button"
                    >
                      {t("account.icalRotateCancel")}
                    </button>
                  </span>
                )}
              </>
            ) : (
              <>
                <p data-testid="ical-not-setup">{t("account.icalNotSetup")}</p>
                <button
                  type="button"
                  onClick={handleRotateIcal}
                  disabled={rotateIcal.isPending}
                  data-testid="ical-get-url-button"
                >
                  {t("account.icalGetUrl")}
                </button>
              </>
            )}
            {icalError && (
              <span role="alert" data-testid="ical-error">
                {icalError}
              </span>
            )}
          </div>

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
                      : sub.type === "agency"
                        ? t("account.subAgencyLabel", { name: sub.agency_name ?? "—" })
                        : t("account.subIssPassLabel")}
                  </strong>{" "}
                  <span>
                    {[
                      sub.notify_email && t("account.channelEmail"),
                      sub.notify_sms && t("account.channelSms"),
                      sub.notify_push && t("account.channelPush"),
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
