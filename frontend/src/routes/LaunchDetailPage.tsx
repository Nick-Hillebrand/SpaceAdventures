import { useEffect } from "react";
import { Link, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useLaunch } from "@/hooks/useLaunch";
import { useLaunchHistory } from "@/hooks/useLaunchHistory";
import { LaunchCard } from "./LaunchCard";
import { formatDateTime } from "@/lib/dateTime";
import type { LaunchHistoryEntry } from "@/types/api";

// Mirrors backend/app/routers/seo.py's SUPPORTED_LANGS — the languages the
// /:lang/launches/:id route accepts and server-renders meta tags for.
const SUPPORTED_LANGS = ["en", "de", "es", "fr", "ja", "ru"];

const HISTORY_TYPE_KEYS: Record<string, string> = {
  net: "launches.historyTypeNet",
  status: "launches.historyTypeStatus",
  gone: "launches.historyTypeGone",
};

function HistoryRow({ entry }: { entry: LaunchHistoryEntry }) {
  const { t } = useTranslation();
  const typeLabel = t(HISTORY_TYPE_KEYS[entry.change_type] ?? entry.change_type);
  return (
    <li className="launch-detail__history-row" data-testid="history-row">
      <span className="launch-detail__history-type">{typeLabel}</span>
      <span className="launch-detail__history-values">
        {entry.old_value && (
          <>
            <span data-testid="history-old-value">{entry.old_value}</span>
            {" → "}
          </>
        )}
        <span data-testid="history-new-value">{entry.new_value}</span>
      </span>
      <time className="launch-detail__history-date" dateTime={entry.detected_at}>
        {formatDateTime(entry.detected_at)}
      </time>
    </li>
  );
}

export default function LaunchDetailPage() {
  const { id = "", lang } = useParams();
  const { t, i18n } = useTranslation();

  // /:lang/launches/:id is the only URL-driven-language route in the app
  // (everywhere else i18n is a client-side-only preference) — it exists so
  // the server can render localized meta tags for each hreflang variant.
  // Sync the client's language to match on mount so the hydrated content
  // agrees with what the server sent, instead of falling back to whatever
  // i18next-browser-languagedetector already resolved.
  useEffect(() => {
    if (lang && SUPPORTED_LANGS.includes(lang) && i18n.resolvedLanguage !== lang) {
      void i18n.changeLanguage(lang);
    }
  }, [lang, i18n]);

  const { data: launch, isLoading } = useLaunch(id);
  const { data: historyData } = useLaunchHistory(id);

  const history = historyData?.data ?? [];

  return (
    <div className="launch-detail-page" data-testid="launch-detail-page">
      <Link to="/launches" className="launch-detail__back" data-testid="back-to-launches">
        {t("launches.detailBackToLaunches")}
      </Link>

      {isLoading && (
        <p className="launch-detail__status" data-testid="launch-detail-loading">
          {t("launches.loadingLaunches")}
        </p>
      )}

      {!isLoading && !launch && (
        <div className="launch-detail__not-found" data-testid="launch-detail-not-found">
          <h1>{t("launches.detailNotFoundTitle")}</h1>
          <p>{t("launches.detailNotFoundHint")}</p>
        </div>
      )}

      {launch && (
        <>
          <LaunchCard launch={launch} />

          <section className="launch-detail__history" data-testid="launch-history">
            <h2>{t("launches.historyTitle")}</h2>
            {history.length === 0 ? (
              <p data-testid="history-empty">{t("launches.historyEmpty")}</p>
            ) : (
              <ul className="launch-detail__history-list">
                {history.map((entry, idx) => (
                  <HistoryRow key={`${entry.change_type}-${entry.detected_at}-${idx}`} entry={entry} />
                ))}
              </ul>
            )}
          </section>
        </>
      )}
    </div>
  );
}
