import { useState, useEffect, useRef } from "react";
import { useTranslation } from "react-i18next";
import type { LaunchData } from "@/types/api";
import { formatDateTime } from "@/lib/dateTime";
import { SubscribeModal } from "@/components/SubscribeModal";
import { useSubscriptions } from "@/hooks/useSubscriptions";

function statusColor(abbrev: string): string {
  switch (abbrev) {
    case "Go":
      return "badge-go";
    case "TBD":
      return "badge-tbd";
    case "Hold":
      return "badge-hold";
    default:
      return "badge-default";
  }
}

function formatCountdown(net: string, statusAbbrev: string): string {
  if (statusAbbrev === "TBD" || statusAbbrev === "Hold") {
    return `NET: ${formatDateTime(net)}`;
  }
  const diff = new Date(net).getTime() - Date.now();
  const abs = Math.abs(diff);
  const sign = diff >= 0 ? "T−" : "T+";
  const totalSec = Math.floor(abs / 1000);
  const days = Math.floor(totalSec / 86400);
  const hours = Math.floor((totalSec % 86400) / 3600);
  const mins = Math.floor((totalSec % 3600) / 60);
  const secs = totalSec % 60;
  if (days > 0) return `${sign} ${days}d ${hours}h ${mins}m ${secs}s`;
  return `${sign} ${hours}h ${mins}m ${secs}s`;
}

interface LaunchCardProps {
  launch: LaunchData;
}

export function LaunchCard({ launch }: LaunchCardProps) {
  const { t } = useTranslation();
  const [countdown, setCountdown] = useState(() =>
    formatCountdown(launch.net, launch.status_abbrev)
  );
  const [expanded, setExpanded] = useState(false);
  const [streamOpen, setStreamOpen] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);
  const { data: subscriptions } = useSubscriptions();

  const isSubscribed = subscriptions?.some(
    (s) =>
      (s.type === "launch" && s.ll2_id === launch.ll2_id) ||
      (s.type === "agency" && s.agency_name === launch.agency_name)
  ) ?? false;

  useEffect(() => {
    const interval = setInterval(() => {
      setCountdown(formatCountdown(launch.net, launch.status_abbrev));
    }, 1000);
    return () => clearInterval(interval);
  }, [launch.net, launch.status_abbrev]);

  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setStreamOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, []);

  const primaryStream = launch.livestream_urls[0];
  const extraStreams = launch.livestream_urls.slice(1);
  const hasStreams = launch.livestream_urls.length > 0;

  return (
    <article
      className="launch-card"
      data-testid="launch-card"
      data-ll2-id={launch.ll2_id}
      aria-label={launch.name}
    >
      {/* Hero Image */}
      <div className="launch-card__image">
        {launch.image_url ? (
          <img
            src={launch.image_url}
            alt={launch.name}
            onError={(e) => {
              (e.target as HTMLImageElement).style.display = "none";
            }}
          />
        ) : (
          <svg
            aria-label="Rocket placeholder"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.5"
          >
            <path d="M12 2C12 2 7 6 7 12v4l5 3 5-3v-4C17 6 12 2 12 2z" />
            <circle cx="12" cy="12" r="2" />
            <path d="M9 21l3 1 3-1" />
          </svg>
        )}
      </div>

      {/* Content */}
      <div className="launch-card__body">
        <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between" }}>
          <h2 className="launch-card__name" data-testid="launch-name">
            {launch.name}
          </h2>
          <button
            type="button"
            aria-label={isSubscribed ? t("subscriptions.subscribedButton") : t("subscriptions.subscribeButton")}
            data-testid="bell-button"
            onClick={() => setModalOpen(true)}
            style={{ background: "none", border: "none", cursor: "pointer", fontSize: "1.25rem" }}
          >
            {isSubscribed ? "🔔" : "🔕"}
          </button>
        </div>

        {/* Status badge */}
        <span
          className={`launch-card__status ${statusColor(launch.status_abbrev)}`}
          data-testid="launch-status"
          aria-label={`Status: ${launch.status_name}`}
        >
          {launch.status_abbrev}
        </span>

        {/* Countdown */}
        <p
          className="launch-card__countdown"
          data-testid="launch-countdown"
          style={{ fontFamily: "monospace" }}
        >
          {countdown}
        </p>

        {/* Agency */}
        <p className="launch-card__agency" data-testid="launch-agency">
          <strong>{launch.agency_name}</strong>
          {launch.agency_type && (
            <span className="launch-card__agency-type"> ({launch.agency_type})</span>
          )}
        </p>

        {/* Rocket */}
        <p className="launch-card__rocket" data-testid="launch-rocket">
          {launch.rocket_name}
          {launch.rocket_family && ` (${launch.rocket_family})`}
        </p>

        {/* Pad */}
        <p className="launch-card__pad" data-testid="launch-pad">
          {launch.pad_name} — {launch.pad_location}
        </p>

        {/* Mission type badge */}
        {launch.mission_type && (
          <span className="launch-card__mission-type" data-testid="launch-mission-type">
            {launch.mission_type}
          </span>
        )}

        {/* Mission description */}
        {launch.mission_description && (
          <div className="launch-card__description">
            <p
              className={expanded ? "" : "launch-card__description--clamped"}
              data-testid="launch-description"
            >
              {launch.mission_description}
            </p>
            <button
              type="button"
              onClick={() => setExpanded((v) => !v)}
              data-testid="description-toggle"
              aria-expanded={expanded}
            >
              {expanded ? t("launches.showLess") : t("launches.showMore")}
            </button>
          </div>
        )}

        {/* Livestream */}
        {hasStreams && (
          <div className="launch-card__streams" ref={dropdownRef}>
            <a
              href={primaryStream.url}
              target="_blank"
              rel="noopener noreferrer"
              data-testid="livestream-button"
              className="launch-card__livestream-btn"
            >
              {t("launches.watchLive")}
            </a>
            {extraStreams.length > 0 && (
              <div className="launch-card__stream-dropdown">
                <button
                  type="button"
                  onClick={() => setStreamOpen((v) => !v)}
                  data-testid="stream-dropdown-toggle"
                  aria-expanded={streamOpen}
                >
                  {t("launches.moreStreams")} ▾
                </button>
                {streamOpen && (
                  <ul role="menu" data-testid="stream-dropdown-menu">
                    {extraStreams.map((s) => (
                      <li key={s.url} role="menuitem">
                        <a
                          href={s.url}
                          target="_blank"
                          rel="noopener noreferrer"
                        >
                          {s.title || s.url}
                        </a>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            )}
          </div>
        )}
      </div>

      {modalOpen && (
        <SubscribeModal
          launch={launch}
          isOpen={modalOpen}
          onClose={() => setModalOpen(false)}
        />
      )}
    </article>
  );
}
