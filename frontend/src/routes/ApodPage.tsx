import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useApod } from "@/hooks/useApod";
import { ErrorBanner } from "@/components/ErrorBanner";
import Skeleton from "@/components/Skeleton";
import EmptyState from "@/components/EmptyState";
import { formatDateTime } from "@/lib/dateTime";

function errorTitleKey(code: string): string {
  switch (code) {
    case "NO_INTERNET": return "error.noInternet";
    case "NASA_UNAVAILABLE": return "error.nasaUnavailable";
    case "NASA_AUTH_ERROR": return "error.nasaAuthError";
    case "NASA_ERROR": return "error.nasaError";
    default: return "common.error";
  }
}

export function todayUtc(): string {
  return new Date().toISOString().slice(0, 10);
}

export function offsetDate(dateStr: string, days: number): string {
  const d = new Date(dateStr + "T00:00:00Z");
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
}

export default function ApodPage() {
  const today = todayUtc();
  const [date, setDate] = useState<string>(today);
  const { t } = useTranslation();
  const { data, isLoading, isError, error, refetch } = useApod(date);

  if (isLoading) {
    return (
      <div className="apod-page">
        <div role="status" aria-label="Loading">
          <span className="sr-only">Loading</span>
          <Skeleton height="2rem" />
          <Skeleton height="400px" />
          <Skeleton height="1.5rem" width="60%" />
          <Skeleton height="1rem" />
          <Skeleton height="1rem" />
        </div>
      </div>
    );
  }

  if (isError && error) {
    return (
      <div className="apod-page">
        <ErrorBanner
          titleKey={errorTitleKey(error.code)}
          detail={error.message}
          onRetry={() => refetch()}
          variant="page"
        />
      </div>
    );
  }

  if (!data) {
    return (
      <div className="apod-page">
        <EmptyState message={t("common.noData")} />
      </div>
    );
  }

  const { data: apod, cached, stale, fetched_at } = data;

  return (
    <div className="apod-page">
      <h1>{t("apod.title")}</h1>

      <label htmlFor="apod-date">
        {t("common.date")}
        <input
          id="apod-date"
          type="date"
          value={date}
          onChange={(event) => setDate(event.target.value)}
        />
      </label>

      <div className="apod-nav-wrapper">
        <button
          className="apod-nav-btn apod-nav-btn--prev"
          aria-label={t("apod.prevDay")}
          onClick={() => setDate(offsetDate(date, -1))}
        >
          ‹
        </button>

        <div className="apod-hero">
          {apod.media_type === "video" ? (
            <iframe
              src={apod.url}
              title={apod.title}
              allow="fullscreen"
              aria-label={apod.title}
            />
          ) : apod.url ? (
            <img src={apod.hdurl ?? apod.url} alt={apod.title} />
          ) : (
            <p>{t("apod.noImage")}</p>
          )}
        </div>

        <button
          className="apod-nav-btn apod-nav-btn--next"
          aria-label={t("apod.nextDay")}
          onClick={() => setDate(offsetDate(date, 1))}
          disabled={date >= today}
        >
          ›
        </button>
      </div>

      <h2>{apod.title}</h2>
      {apod.copyright ? <p className="apod-copyright">© {apod.copyright}</p> : null}
      <p className="apod-explanation">{apod.explanation}</p>

      <p className="apod-badge" aria-label={cached ? "cached" : "live"}>
        {stale
          ? t("error.staleData", { date: formatDateTime(fetched_at) })
          : cached
            ? `${t("common.cached")} · ${t("common.fetchedAt")} ${formatDateTime(fetched_at)}`
            : `${t("common.live")} · ${t("common.fetchedAt")} ${formatDateTime(fetched_at)}`}
      </p>
    </div>
  );
}
