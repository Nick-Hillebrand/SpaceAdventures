import type { ReactNode } from "react";

export type ErrorBannerVariant = "page" | "section";

export interface ErrorBannerProps {
  title: string;
  detail?: string;
  onRetry?: () => void;
  action?: ReactNode;
  variant?: ErrorBannerVariant;
}

export function ErrorBanner({
  title,
  detail,
  onRetry,
  action,
  variant = "section",
}: ErrorBannerProps) {
  return (
    <div role="alert" data-variant={variant} className={`error-banner error-banner--${variant}`}>
      <h2>{title}</h2>
      {detail ? <p>{detail}</p> : null}
      {onRetry ? (
        <button type="button" onClick={onRetry}>
          Retry
        </button>
      ) : null}
      {action}
    </div>
  );
}
