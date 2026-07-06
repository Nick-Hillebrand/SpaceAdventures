import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { apiPost } from "@/lib/api";

export default function ConfirmUnsubscribePage() {
  const [searchParams] = useSearchParams();
  const { t } = useTranslation();
  const token = searchParams.get("token") ?? "";
  const [status, setStatus] = useState<"idle" | "success" | "error">("idle");
  const [errorMessage, setErrorMessage] = useState<string>("");

  async function handleUnsubscribe() {
    try {
      await apiPost("/api/v1/subscriptions/unsubscribe", { token });
      setStatus("success");
    } catch (err: unknown) {
      const e = err as { message?: string };
      setErrorMessage(e?.message ?? t("common.error"));
      setStatus("error");
    }
  }

  if (status === "success") {
    return (
      <div data-testid="unsubscribe-success">
        <h1>{t("subscriptions.unsubscribedTitle")}</h1>
        <p>{t("subscriptions.unsubscribedSuccess")}</p>
      </div>
    );
  }

  return (
    <div data-testid="confirm-unsubscribe-page">
      <h1>{t("subscriptions.confirmUnsubscribeTitle")}</h1>
      <p>{t("subscriptions.confirmUnsubscribeText")}</p>

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
        {t("subscriptions.confirmButton")}
      </button>
    </div>
  );
}
