import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";

export type ErrorBannerVariant = "page" | "section";

export interface ErrorBannerProps {
  titleKey: string;
  detailKey?: string;
  detailValues?: Record<string, unknown>;
  detail?: string;
  onRetry?: () => void;
  action?: ReactNode;
  variant?: ErrorBannerVariant;
}

export function ErrorBanner({
  titleKey,
  detailKey,
  detailValues,
  detail,
  onRetry,
  action,
  variant = "section",
}: ErrorBannerProps) {
  const { t } = useTranslation();

  return (
    <div role="alert" data-variant={variant} className={`error-banner error-banner--${variant}`}>
      <h2>{t(titleKey)}</h2>
      {detailKey ? <p>{t(detailKey, detailValues)}</p> : null}
      {!detailKey && detail ? <p>{detail}</p> : null}
      {onRetry ? (
        <button type="button" onClick={onRetry}>
          {t("common.retry")}
        </button>
      ) : null}
      {action}
    </div>
  );
}
