import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { apiPost } from "@/lib/api";

export default function ConfirmUnsubscribePage() {
  const [searchParams] = useSearchParams();
  const token = searchParams.get("token") ?? "";
  const [status, setStatus] = useState<"idle" | "success" | "error">("idle");
  const [errorMessage, setErrorMessage] = useState<string>("");

  async function handleUnsubscribe() {
    try {
      await apiPost("/api/v1/subscriptions/unsubscribe", { token });
      setStatus("success");
    } catch (err: unknown) {
      const e = err as { message?: string };
      setErrorMessage(e?.message ?? "An error occurred. Please try again.");
      setStatus("error");
    }
  }

  if (status === "success") {
    return (
      <div data-testid="unsubscribe-success">
        <h1>Unsubscribed</h1>
        <p>You have been unsubscribed successfully.</p>
      </div>
    );
  }

  return (
    <div data-testid="confirm-unsubscribe-page">
      <h1>Confirm Unsubscribe</h1>
      <p>Click the button below to confirm that you want to unsubscribe from launch notifications.</p>

      {status === "error" && (
        <p data-testid="unsubscribe-error" style={{ color: "red" }}>
          {errorMessage}
        </p>
      )}

      <button
        type="button"
        onClick={handleUnsubscribe}
        data-testid="confirm-unsubscribe-button"
      >
        Confirm Unsubscribe
      </button>
    </div>
  );
}
