import { useState } from "react";
import { useApod } from "@/hooks/useApod";
import { ErrorBanner } from "@/components/ErrorBanner";
import { formatDateTime } from "@/lib/dateTime";

function errorTitle(code: string): string {
  switch (code) {
    case "NO_INTERNET":
      return "No internet connection";
    case "NASA_UNAVAILABLE":
      return "NASA services are currently unavailable";
    case "NASA_AUTH_ERROR":
      return "Invalid NASA API Key";
    case "NASA_ERROR":
      return "NASA returned an error";
    default:
      return "Something went wrong";
  }
}

export default function ApodPage() {
  const [date, setDate] = useState<string>("");
  const { data, isLoading, isError, error, refetch } = useApod(date || undefined);

  if (isLoading) {
    return (
      <div className="apod-page">
        <p role="status">Loading…</p>
      </div>
    );
  }

  if (isError && error) {
    return (
      <div className="apod-page">
        <ErrorBanner
          title={errorTitle(error.code)}
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
        <p>No data available</p>
      </div>
    );
  }

  const { data: apod, cached, stale, fetched_at } = data;

  return (
    <div className="apod-page">
      <h1>Astronomy Picture of the Day</h1>

      <label htmlFor="apod-date">
        Date
        <input
          id="apod-date"
          type="date"
          value={date}
          onChange={(event) => setDate(event.target.value)}
        />
      </label>

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
          <p>No image available</p>
        )}
      </div>

      <h2>{apod.title}</h2>
      {apod.copyright ? <p className="apod-copyright">© {apod.copyright}</p> : null}
      <p className="apod-explanation">{apod.explanation}</p>

      <p className="apod-badge" aria-label={cached ? "cached" : "live"}>
        {stale
          ? `Showing cached data from ${formatDateTime(fetched_at)}`
          : cached
            ? `Served from cache · fetched ${formatDateTime(fetched_at)}`
            : `Live · fetched ${formatDateTime(fetched_at)}`}
      </p>
    </div>
  );
}
