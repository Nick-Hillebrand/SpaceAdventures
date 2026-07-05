import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useMe } from "@/hooks/useAuth";
import { apiPost } from "@/lib/api";

type Tab = "profile" | "subscriptions";

export default function AccountPage() {
  const navigate = useNavigate();
  const { data: user, isLoading, isError, error } = useMe();
  const [activeTab, setActiveTab] = useState<Tab>("profile");
  const [resendStatus, setResendStatus] = useState<Record<string, string>>({});

  // If 401 (not authenticated), redirect to login
  if (isError && error && error.status === 401) {
    navigate("/login?return=/account");
    return null;
  }

  if (isLoading) {
    return <p role="status">Loading…</p>;
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
      <h1>My Account</h1>
      <nav>
        <button
          type="button"
          onClick={() => setActiveTab("profile")}
          aria-selected={activeTab === "profile"}
        >
          Profile
        </button>
        <button
          type="button"
          onClick={() => setActiveTab("subscriptions")}
          aria-selected={activeTab === "subscriptions"}
        >
          Subscriptions
        </button>
      </nav>

      {activeTab === "profile" && (
        <div>
          <p>
            <strong>Name:</strong> {user.first_name} {user.last_name}
          </p>
          {user.email && (
            <p>
              <strong>Email:</strong> {user.email}{" "}
              {user.email_verified ? (
                <span aria-label="email verified">✓ Verified</span>
              ) : (
                <>
                  <span>Not verified</span>
                  <button type="button" onClick={() => handleResend("email")}>
                    Resend OTP
                  </button>
                  {resendStatus.email && <span>{resendStatus.email}</span>}
                </>
              )}
            </p>
          )}
          {user.phone && (
            <p>
              <strong>Phone:</strong> {user.phone}{" "}
              {user.phone_verified ? (
                <span aria-label="phone verified">✓ Verified</span>
              ) : (
                <>
                  <span>Not verified</span>
                  <button type="button" onClick={() => handleResend("phone")}>
                    Resend OTP
                  </button>
                  {resendStatus.phone && <span>{resendStatus.phone}</span>}
                </>
              )}
            </p>
          )}
          <p>
            <strong>Member since:</strong>{" "}
            {new Date(user.created_at).toLocaleDateString()}
          </p>
        </div>
      )}

      {activeTab === "subscriptions" && (
        <div>
          <p>Subscriptions coming soon.</p>
        </div>
      )}
    </div>
  );
}
