import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useMe, useSetConsent } from "@/hooks/useAuth";
import {
  useCreateSubscription,
  useSubscriptions,
} from "@/hooks/useSubscriptions";
import { usePush } from "@/hooks/usePush";
import type { LaunchData } from "@/types/api";
import { formatDateTime } from "@/lib/dateTime";

interface SubscribeModalProps {
  launch: LaunchData;
  isOpen: boolean;
  onClose: () => void;
}

export function SubscribeModal({ launch, isOpen, onClose }: SubscribeModalProps) {
  const { t } = useTranslation();
  const { data: user, isError: isMeError, error: meError } = useMe();
  const { data: subscriptions } = useSubscriptions();
  const createSubscription = useCreateSubscription();
  const setConsent = useSetConsent();
  const push = usePush();

  const [subscribeLaunch, setSubscribeLaunch] = useState(false);
  const [subscribeAgency, setSubscribeAgency] = useState(false);
  const [notifyEmail, setNotifyEmail] = useState(false);
  const [notifySms, setNotifySms] = useState(false);
  const [notifyPush, setNotifyPush] = useState(false);
  const [grantConsent, setGrantConsent] = useState(false);
  const [status, setStatus] = useState<string | null>(null);

  if (!isOpen) return null;

  const isUnauthenticated = isMeError && meError && meError.status === 401;
  const hasConsent = !!user?.consent_notifications_at;

  const isLaunchSubscribed = subscriptions?.some(
    (s) => s.type === "launch" && s.ll2_id === launch.ll2_id
  ) ?? false;

  const isAgencySubscribed = subscriptions?.some(
    (s) => s.type === "agency" && s.agency_name === launch.agency_name
  ) ?? false;

  async function handleConfirm() {
    if (!user) return;
    if (!hasConsent) {
      if (!grantConsent) return;
      try {
        await setConsent.mutateAsync(true);
      } catch {
        setStatus(t("subscriptions.failedSubscribe"));
        return;
      }
    }
    if ((subscribeLaunch || subscribeAgency) && notifyPush && !push.isSubscribed) {
      const pushSubscribed = await push.subscribe();
      if (!pushSubscribed) {
        setStatus(t("subscriptions.failedSubscribe"));
        return;
      }
    }

    const tasks = [];

    if (subscribeLaunch && !isLaunchSubscribed) {
      tasks.push(
        createSubscription.mutateAsync({
          type: "launch",
          ll2_id: launch.ll2_id,
          notify_email: notifyEmail,
          notify_sms: notifySms,
          notify_push: notifyPush,
        })
      );
    }

    if (subscribeAgency && !isAgencySubscribed) {
      tasks.push(
        createSubscription.mutateAsync({
          type: "agency",
          agency_name: launch.agency_name,
          notify_email: notifyEmail,
          notify_sms: notifySms,
          notify_push: notifyPush,
        })
      );
    }

    if (tasks.length === 0) {
      onClose();
      return;
    }

    try {
      await Promise.all(tasks);
      setStatus(t("subscriptions.success"));
      setTimeout(onClose, 1500);
    } catch {
      setStatus(t("subscriptions.failedSubscribe"));
    }
  }

  const hasVerifiedEmail = user?.email_verified && !!user?.email;
  const hasVerifiedPhone = user?.phone_verified && !!user?.phone;
  const pushAvailable = push.permission !== "unsupported" && push.permission !== "denied";
  const noChannelAvailable = !hasVerifiedEmail && !hasVerifiedPhone && !pushAvailable;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label={t("subscriptions.modalTitle")}
      data-testid="subscribe-modal"
      style={{ position: "fixed", inset: 0, zIndex: 50 }}
    >
      <div
        style={{ position: "absolute", inset: 0, background: "rgba(0,0,0,0.5)" }}
        onClick={onClose}
      />
      <div className="subscribe-modal__panel">
        <button
          type="button"
          onClick={onClose}
          aria-label={t("common.close")}
          className="modal-close"
        >
          ✕
        </button>

        <h2>{t("subscriptions.modalTitle")}</h2>

        {isUnauthenticated ? (
          <div data-testid="login-prompt">
            <p>{t("subscriptions.loginRequired")}</p>
            <a
              href={`/login?return=/launches`}
              data-testid="login-link"
            >
              {t("subscriptions.logIn")}
            </a>
            {" | "}
            <a
              href={`/register?return=/launches`}
              data-testid="register-link"
            >
              {t("subscriptions.register")}
            </a>
          </div>
        ) : user ? (
          <div>
            <fieldset>
              <legend>{t("subscriptions.subscribeTo")}</legend>
              <label>
                <input
                  type="checkbox"
                  checked={subscribeLaunch}
                  onChange={(e) => setSubscribeLaunch(e.target.checked)}
                  data-testid="checkbox-launch"
                />
                {" "}{t("subscriptions.thisLaunch")}: <strong>{launch.name}</strong>
                <br />
                <small>{t("launches.netLabel")}: {formatDateTime(launch.net)}</small>
              </label>
              <br />
              <label>
                <input
                  type="checkbox"
                  checked={subscribeAgency}
                  onChange={(e) => setSubscribeAgency(e.target.checked)}
                  data-testid="checkbox-agency"
                />
                {" "}{t("subscriptions.allFromAgency", { agency: launch.agency_name })}
              </label>
            </fieldset>

            <fieldset>
              <legend>{t("subscriptions.notifyVia")}</legend>
              {hasVerifiedEmail ? (
                <label>
                  <input
                    type="checkbox"
                    checked={notifyEmail}
                    onChange={(e) => setNotifyEmail(e.target.checked)}
                    data-testid="checkbox-email"
                  />
                  {" "}{t("account.channelEmail")} ({user.email})
                </label>
              ) : (
                <p data-testid="verify-email-prompt">
                  {t("subscriptions.verifyEmailPrompt")}
                </p>
              )}
              <br />
              {hasVerifiedPhone ? (
                <label>
                  <input
                    type="checkbox"
                    checked={notifySms}
                    onChange={(e) => setNotifySms(e.target.checked)}
                    data-testid="checkbox-sms"
                  />
                  {" "}{t("account.channelSms")} ({user.phone})
                </label>
              ) : (
                <p data-testid="verify-phone-prompt">
                  {t("subscriptions.verifyPhonePrompt")}
                </p>
              )}
              <br />
              {push.permission !== "unsupported" && push.permission !== "denied" && (
                <label>
                  <input
                    type="checkbox"
                    checked={notifyPush}
                    onChange={(e) => setNotifyPush(e.target.checked)}
                    data-testid="checkbox-push"
                  />
                  {" "}{t("account.channelPush")}
                </label>
              )}
              {push.permission === "denied" && (
                <p data-testid="push-denied-prompt">
                  {t("subscriptions.pushDeniedPrompt")}
                </p>
              )}
            </fieldset>

            {noChannelAvailable && (
              <p data-testid="no-channel-prompt" style={{ color: "var(--color-text-muted)" }}>
                {t("subscriptions.verifyChannelPrompt")}
              </p>
            )}

            {!hasConsent && (
              <fieldset data-testid="consent-prompt">
                <legend>{t("subscriptions.consentRequiredTitle")}</legend>
                <p>{t("subscriptions.consentRequiredPrompt")}</p>
                <label>
                  <input
                    type="checkbox"
                    checked={grantConsent}
                    onChange={(e) => setGrantConsent(e.target.checked)}
                    data-testid="checkbox-consent"
                  />
                  {" "}{t("auth.consentNotifications")}
                </label>
              </fieldset>
            )}

            {status && <p data-testid="subscribe-status">{status}</p>}

            <div className="modal-actions">
              <button
                type="button"
                onClick={handleConfirm}
                data-testid="confirm-subscribe"
                disabled={createSubscription.isPending || setConsent.isPending || (!hasConsent && !grantConsent)}
              >
                {t("subscriptions.confirm")}
              </button>
              <button type="button" onClick={onClose}>
                {t("subscriptions.cancel")}
              </button>
            </div>
          </div>
        ) : (
          <p>{t("common.loading")}</p>
        )}
      </div>
    </div>
  );
}
