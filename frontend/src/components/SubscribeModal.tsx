import { useState } from "react";
import { useMe } from "@/hooks/useAuth";
import {
  useCreateSubscription,
  useSubscriptions,
} from "@/hooks/useSubscriptions";
import type { LaunchData } from "@/types/api";
import { formatDateTime } from "@/lib/dateTime";

interface SubscribeModalProps {
  launch: LaunchData;
  isOpen: boolean;
  onClose: () => void;
}

export function SubscribeModal({ launch, isOpen, onClose }: SubscribeModalProps) {
  const { data: user, isError: isMeError, error: meError } = useMe();
  const { data: subscriptions } = useSubscriptions();
  const createSubscription = useCreateSubscription();

  const [subscribeLaunch, setSubscribeLaunch] = useState(false);
  const [subscribeAgency, setSubscribeAgency] = useState(false);
  const [notifyEmail, setNotifyEmail] = useState(false);
  const [notifySms, setNotifySms] = useState(false);
  const [status, setStatus] = useState<string | null>(null);

  if (!isOpen) return null;

  const isUnauthenticated = isMeError && meError && meError.status === 401;

  // Check if already subscribed to this launch
  const isLaunchSubscribed = subscriptions?.some(
    (s) => s.type === "launch" && s.ll2_id === launch.ll2_id
  ) ?? false;

  const isAgencySubscribed = subscriptions?.some(
    (s) => s.type === "agency" && s.agency_name === launch.agency_name
  ) ?? false;

  async function handleConfirm() {
    if (!user) return;
    const tasks = [];

    if (subscribeLaunch && !isLaunchSubscribed) {
      tasks.push(
        createSubscription.mutateAsync({
          type: "launch",
          ll2_id: launch.ll2_id,
          notify_email: notifyEmail,
          notify_sms: notifySms,
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
        })
      );
    }

    if (tasks.length === 0) {
      onClose();
      return;
    }

    try {
      await Promise.all(tasks);
      setStatus("Subscribed successfully!");
      setTimeout(onClose, 1500);
    } catch {
      setStatus("Failed to subscribe. Please try again.");
    }
  }

  const hasVerifiedEmail = user?.email_verified && !!user?.email;
  const hasVerifiedPhone = user?.phone_verified && !!user?.phone;
  const noChannelAvailable = !hasVerifiedEmail && !hasVerifiedPhone;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Subscribe to launch updates"
      data-testid="subscribe-modal"
      style={{ position: "fixed", inset: 0, zIndex: 50 }}
    >
      <div
        style={{ position: "absolute", inset: 0, background: "rgba(0,0,0,0.5)" }}
        onClick={onClose}
      />
      <div
        style={{
          position: "relative",
          margin: "10vh auto",
          maxWidth: 480,
          background: "#fff",
          borderRadius: 8,
          padding: 24,
          zIndex: 1,
        }}
      >
        <button
          type="button"
          onClick={onClose}
          aria-label="Close"
          style={{ position: "absolute", top: 12, right: 12 }}
        >
          ✕
        </button>

        <h2>Subscribe to Updates</h2>

        {isUnauthenticated ? (
          <div data-testid="login-prompt">
            <p>Log in to subscribe to launch notifications.</p>
            <a
              href={`/login?return=/launches`}
              data-testid="login-link"
            >
              Log In
            </a>
            {" | "}
            <a
              href={`/register?return=/launches`}
              data-testid="register-link"
            >
              Register
            </a>
          </div>
        ) : user ? (
          <div>
            {/* What to subscribe to */}
            <fieldset>
              <legend>Subscribe to:</legend>
              <label>
                <input
                  type="checkbox"
                  checked={subscribeLaunch}
                  onChange={(e) => setSubscribeLaunch(e.target.checked)}
                  data-testid="checkbox-launch"
                />
                {" "}This launch: <strong>{launch.name}</strong>
                <br />
                <small>NET: {formatDateTime(launch.net)}</small>
              </label>
              <br />
              <label>
                <input
                  type="checkbox"
                  checked={subscribeAgency}
                  onChange={(e) => setSubscribeAgency(e.target.checked)}
                  data-testid="checkbox-agency"
                />
                {" "}All <strong>{launch.agency_name}</strong> launches
              </label>
            </fieldset>

            {/* Notification channels */}
            <fieldset style={{ marginTop: 12 }}>
              <legend>Notify me via:</legend>
              {hasVerifiedEmail ? (
                <label>
                  <input
                    type="checkbox"
                    checked={notifyEmail}
                    onChange={(e) => setNotifyEmail(e.target.checked)}
                    data-testid="checkbox-email"
                  />
                  {" "}Email ({user.email})
                </label>
              ) : (
                <p data-testid="verify-email-prompt">
                  Verify your email in Account Settings to enable email notifications.
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
                  {" "}SMS ({user.phone})
                </label>
              ) : (
                <p data-testid="verify-phone-prompt">
                  Verify your phone in Account Settings to enable SMS notifications.
                </p>
              )}
            </fieldset>

            {noChannelAvailable && (
              <p data-testid="no-channel-prompt" style={{ color: "#888" }}>
                Verify your email or phone in Account Settings to receive notifications.
              </p>
            )}

            {status && <p data-testid="subscribe-status">{status}</p>}

            <div style={{ marginTop: 16, display: "flex", gap: 8 }}>
              <button
                type="button"
                onClick={handleConfirm}
                data-testid="confirm-subscribe"
                disabled={createSubscription.isPending}
              >
                Confirm
              </button>
              <button type="button" onClick={onClose}>
                Cancel
              </button>
            </div>
          </div>
        ) : (
          <p>Loading…</p>
        )}
      </div>
    </div>
  );
}
