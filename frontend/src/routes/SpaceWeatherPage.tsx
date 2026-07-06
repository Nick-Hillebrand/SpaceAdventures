import { useState, useMemo, type ReactElement } from "react";
import { useTranslation } from "react-i18next";
import { useSpaceWeatherEvents } from "@/hooks/useSpaceWeather";
import { ErrorBanner } from "@/components/ErrorBanner";
import { formatDate, formatDateTime } from "@/lib/dateTime";
import type { SpaceWeatherEventData, SpaceWeatherEventType } from "@/types/api";

type Tab = SpaceWeatherEventType;

const TABS = [
  { id: "FLR" as Tab, labelKey: "spaceWeather.flares" },
  { id: "GST" as Tab, labelKey: "spaceWeather.storms" },
  { id: "CME" as Tab, labelKey: "spaceWeather.cme" },
  { id: "SEP" as Tab, labelKey: "spaceWeather.sep" },
  { id: "RBE" as Tab, labelKey: "spaceWeather.rbe" },
];

const TAB_COLORS: Record<Tab, string> = {
  FLR: "#fb923c",
  GST: "#a78bfa",
  CME: "#facc15",
  SEP: "#34d399",
  RBE: "#38bdf8",
};

// ── Icons ──────────────────────────────────────────────────────────────────────

function IconFlare() {
  return (
    <svg aria-hidden="true" viewBox="0 0 24 24" fill="currentColor" className="sw-tab-icon">
      <path d="M12 2a1 1 0 0 1 1 1v2a1 1 0 0 1-2 0V3a1 1 0 0 1 1-1zm5.657 3.636a1 1 0 0 1 0 1.414l-1.414 1.414a1 1 0 0 1-1.414-1.414l1.414-1.414a1 1 0 0 1 1.414 0zm-11.314 0a1 1 0 0 1 1.414 0l1.414 1.414a1 1 0 0 1-1.414 1.414L6.343 7.05a1 1 0 0 1 0-1.414zM12 7a5 5 0 1 1 0 10A5 5 0 0 1 12 7zm7 4a1 1 0 0 1 0 2h-2a1 1 0 0 1 0-2h2zM7 11a1 1 0 0 1 0 2H5a1 1 0 0 1 0-2h2zm9.95 4.243a1 1 0 0 1 0 1.414l-1.414 1.414a1 1 0 0 1-1.414-1.414l1.414-1.414a1 1 0 0 1 1.414 0zM7.464 15.05a1 1 0 0 1 1.414 1.414L7.464 17.878a1 1 0 0 1-1.414-1.414l1.414-1.414zM12 19a1 1 0 0 1 1 1v2a1 1 0 0 1-2 0v-2a1 1 0 0 1 1-1z"/>
    </svg>
  );
}

function IconStorm() {
  return (
    <svg aria-hidden="true" viewBox="0 0 24 24" fill="currentColor" className="sw-tab-icon">
      <path d="M12 3a9 9 0 0 1 8.66 11.495A4.5 4.5 0 0 1 17.5 22H6a4 4 0 0 1 0-8h.08A9 9 0 0 1 12 3zm-1 10h-2l-1 4h2l-1 3 4-5h-2l1-2z"/>
    </svg>
  );
}

function IconCme() {
  return (
    <svg aria-hidden="true" viewBox="0 0 24 24" fill="currentColor" className="sw-tab-icon">
      <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1.41 16.09V20h-2.67v-1.93c-1.71-.36-3.16-1.46-3.27-3.4h1.96c.1 1.05.82 1.87 2.65 1.87 1.96 0 2.4-.98 2.4-1.59 0-.83-.44-1.61-2.67-2.14-2.48-.6-4.18-1.62-4.18-3.67 0-1.72 1.39-2.84 3.11-3.21V4h2.67v1.95c1.86.45 2.79 1.86 2.85 3.39H14.3c-.05-1.11-.64-1.87-2.22-1.87-1.5 0-2.4.68-2.4 1.64 0 .84.65 1.39 2.67 1.91s4.18 1.39 4.18 3.91c-.01 1.83-1.38 2.83-3.12 3.16z"/>
    </svg>
  );
}

function IconSep() {
  return (
    <svg aria-hidden="true" viewBox="0 0 24 24" fill="currentColor" className="sw-tab-icon">
      <path d="M7 2v11h3v9l7-12h-4l4-8z"/>
    </svg>
  );
}

function IconRbe() {
  return (
    <svg aria-hidden="true" viewBox="0 0 24 24" fill="currentColor" className="sw-tab-icon">
      <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm0 18c-4.42 0-8-3.58-8-8s3.58-8 8-8 8 3.58 8 8-3.58 8-8 8zm0-13a5 5 0 1 0 0 10A5 5 0 0 0 12 7zm0 8a3 3 0 1 1 0-6 3 3 0 0 1 0 6zm0-5a2 2 0 1 0 0 4 2 2 0 0 0 0-4z"/>
    </svg>
  );
}

const TAB_ICONS: Record<Tab, ReactElement> = {
  FLR: <IconFlare />,
  GST: <IconStorm />,
  CME: <IconCme />,
  SEP: <IconSep />,
  RBE: <IconRbe />,
};

// ── Helpers ────────────────────────────────────────────────────────────────────

function errorTitleKey(code: string): string {
  switch (code) {
    case "NO_INTERNET": return "error.noInternet";
    case "NASA_UNAVAILABLE": return "error.nasaUnavailable";
    case "NASA_AUTH_ERROR": return "error.nasaAuthError";
    default: return "common.error";
  }
}

function todayIso(): string {
  const now = new Date();
  return `${now.getUTCFullYear()}-${String(now.getUTCMonth() + 1).padStart(2, "0")}-${String(now.getUTCDate()).padStart(2, "0")}`;
}

function addDaysIso(iso: string, days: number): string {
  const d = new Date(`${iso}T00:00:00Z`);
  if (Number.isNaN(d.getTime())) return iso;
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
}

function parseRaw(raw: string): Record<string, unknown> {
  try { return JSON.parse(raw) as Record<string, unknown>; }
  catch { return {}; }
}

function renderTimestamp(value: unknown): string {
  if (typeof value === "string" && value.length >= 10) {
    try { return formatDateTime(value); }
    catch { return String(value); }
  }
  return value != null ? String(value) : "—";
}

// ── Type-specific highlights ───────────────────────────────────────────────────

const FLR_LEVELS = ["A", "B", "C", "M", "X"] as const;
const FLR_COLORS = ["#9ca3af", "#22c55e", "#eab308", "#f97316", "#ef4444"];
const FLR_LETTER_COLORS: Record<string, string> = {
  X: "#ef4444", M: "#f97316", C: "#facc15", B: "#22c55e", A: "#9ca3af",
};

function FlareHighlight({ classType }: { classType: string }) {
  const letter = classType[0]?.toUpperCase() ?? "";
  const number = classType.slice(1);
  const levelIdx = (FLR_LEVELS as readonly string[]).indexOf(letter);
  const color = FLR_LETTER_COLORS[letter] ?? "#9ca3af";

  return (
    <div className="sw-flare-class">
      <div className="sw-flare-label">
        <span className="sw-class-letter" style={{ color }}>{letter}</span>
        {number && <span className="sw-class-number" style={{ color }}>{number}</span>}
      </div>
      <div className="sw-class-bar">
        {FLR_LEVELS.map((l, i) => (
          <div
            key={l}
            className="sw-class-segment"
            style={{ background: i <= levelIdx ? FLR_COLORS[i] : undefined, opacity: i <= levelIdx ? 1 : 0.2 }}
          />
        ))}
      </div>
    </div>
  );
}

function StormHighlight({ data }: { data: Record<string, unknown> }) {
  const allKp = Array.isArray(data.allKpIndex) ? data.allKpIndex : [];
  const kpValues = allKp
    .map((k: unknown) => (k && typeof k === "object" ? (k as Record<string, unknown>).kpIndex : null))
    .filter((v): v is number => typeof v === "number");
  if (kpValues.length === 0) return null;

  const maxKp = Math.max(...kpValues);
  const kpColor = maxKp >= 8 ? "#ef4444" : maxKp >= 6 ? "#f97316" : maxKp >= 4 ? "#eab308" : "#22c55e";
  const label = maxKp >= 8 ? "Extreme" : maxKp >= 6 ? "Severe" : maxKp >= 5 ? "Strong" : maxKp >= 4 ? "Moderate" : "Minor";

  return (
    <div className="sw-kp-gauge">
      <div className="sw-kp-header">
        <span className="sw-kp-label">Kp</span>
        <span className="sw-kp-value" style={{ color: kpColor }}>{maxKp}</span>
      </div>
      <span className="sw-kp-class" style={{ color: kpColor }}>{label}</span>
      <div className="sw-kp-bar">
        {Array.from({ length: 9 }, (_, i) => (
          <div
            key={i}
            className="sw-kp-segment"
            style={{ background: i < maxKp ? kpColor : undefined, opacity: i < maxKp ? 1 : 0.15 }}
          />
        ))}
      </div>
    </div>
  );
}

function CmeHighlight({ data }: { data: Record<string, unknown> }) {
  const analyses = Array.isArray(data.cmeAnalyses) ? data.cmeAnalyses : [];
  const first = analyses[0] as Record<string, unknown> | undefined;
  const speed = first && typeof first.speed === "number" ? first.speed : null;
  const type = first && typeof first.type === "string" ? first.type : null;
  if (!speed && !type) return null;

  return (
    <div className="sw-cme-highlight">
      {speed !== null && (
        <div className="sw-cme-speed">
          {Math.round(speed)}<small>km/s</small>
        </div>
      )}
      {type && <span className="sw-cme-type-badge">{type}</span>}
    </div>
  );
}

// ── Activity Timeline ──────────────────────────────────────────────────────────

function ActivityTimeline({ events, start, end, color }: {
  events: SpaceWeatherEventData[];
  start: string;
  end: string;
  color: string;
}) {
  const bars = useMemo(() => {
    const startMs = new Date(`${start}T00:00:00Z`).getTime();
    const endMs = new Date(`${end}T23:59:59Z`).getTime();
    if (Number.isNaN(startMs) || Number.isNaN(endMs)) return [];
    const msPerDay = 86_400_000;
    const totalDays = Math.max(1, Math.round((endMs - startMs) / msPerDay) + 1);
    const counts: Record<string, number> = {};
    for (let i = 0; i < totalDays; i++) {
      counts[new Date(startMs + i * msPerDay).toISOString().slice(0, 10)] = 0;
    }
    for (const e of events) {
      const day = e.start_date.slice(0, 10);
      if (day in counts) counts[day]++;
    }
    const max = Math.max(...Object.values(counts), 1);
    return Object.entries(counts).map(([date, count]) => ({
      date,
      count,
      h: count === 0 ? 0 : Math.max(0.08, count / max),
    }));
  }, [events, start, end]);

  if (bars.length < 3 || events.length === 0) return null;

  const totalEvents = events.length;
  const activeDays = bars.filter((b) => b.count > 0).length;

  return (
    <div className="sw-timeline" aria-hidden="true">
      <div className="sw-timeline-header">
        <span className="sw-timeline-stat">{totalEvents} events over {activeDays} active day{activeDays !== 1 ? "s" : ""}</span>
      </div>
      <div className="sw-timeline-bars">
        {bars.map(({ date, count, h }) => (
          <div key={date} className="sw-timeline-bar-wrap" title={count > 0 ? `${date}: ${count} event${count !== 1 ? "s" : ""}` : date}>
            <div
              className="sw-timeline-bar"
              style={{ height: `${h * 100}%`, background: color }}
            />
          </div>
        ))}
      </div>
      <div className="sw-timeline-labels">
        <span>{start}</span>
        <span>{end}</span>
      </div>
    </div>
  );
}

// ── EventCard ──────────────────────────────────────────────────────────────────

const TIME_FIELDS = ["beginTime", "startTime", "eventTime", "peakTime", "endTime"] as const;
const TIME_SET = new Set<string>(TIME_FIELDS);
// Keys shown in type-specific highlights — hide from generic dl (but FLR classType stays in dl for tests)
const HIGHLIGHT_KEYS: Record<Tab, Set<string>> = {
  FLR: new Set(),
  GST: new Set(["allKpIndex"]),
  CME: new Set(["cmeAnalyses"]),
  SEP: new Set(),
  RBE: new Set(),
};

function EventCard({ event }: { event: SpaceWeatherEventData }) {
  const data = parseRaw(event.raw_json);
  const hKeys = HIGHLIGHT_KEYS[event.event_type];

  const timeFields = TIME_FIELDS.filter(
    (k) => typeof data[k] === "string" && (data[k] as string).length >= 10,
  );
  const noteFields = Object.entries(data).filter(
    ([k]) => !TIME_SET.has(k) && !k.endsWith("ID") && k !== "activityID" && !hKeys.has(k),
  );

  const renderHighlight = () => {
    switch (event.event_type) {
      case "FLR": {
        const ct = typeof data.classType === "string" ? data.classType : null;
        return ct ? <FlareHighlight classType={ct} /> : null;
      }
      case "GST": return <StormHighlight data={data} />;
      case "CME": return <CmeHighlight data={data} />;
      default: return null;
    }
  };

  return (
    <article
      className={`sw-card sw-card--${event.event_type}`}
      data-type={event.event_type}
      aria-label={`${event.event_type} event ${event.id}`}
    >
      <header className="sw-card-header">
        <div className="sw-card-meta">
          <span className="sw-card-badge">{event.event_type}</span>
          <time className="sw-card-date" dateTime={event.start_date}>{formatDate(event.start_date)}</time>
        </div>
        {renderHighlight()}
      </header>
      <dl className="sw-card-fields">
        {timeFields.map((field) => (
          <div key={field} className="sw-card-row sw-card-row--time">
            <dt>{field}</dt>
            <dd>{renderTimestamp(data[field])}</dd>
          </div>
        ))}
        {noteFields.slice(0, 4).map(([key, val]) => (
          <div key={key} className="sw-card-row">
            <dt>{key}</dt>
            <dd className="sw-card-value">
              {typeof val === "object" ? JSON.stringify(val) : String(val ?? "—")}
            </dd>
          </div>
        ))}
      </dl>
    </article>
  );
}

// ── TabPanel ──────────────────────────────────────────────────────────────────

function TabPanel({ eventType, start, end }: { eventType: Tab; start: string; end: string }) {
  const { t } = useTranslation();
  const { data, isLoading, isError, error, refetch } = useSpaceWeatherEvents(eventType, start, end);

  if (isLoading) {
    return <p role="status" className="sw-loading">{t("common.loading")}</p>;
  }

  if (isError && error) {
    return (
      <ErrorBanner
        titleKey={errorTitleKey(error.code)}
        detail={error.message}
        onRetry={() => refetch()}
        variant="section"
      />
    );
  }

  if (!data || data.data.length === 0) {
    return <p className="sw-empty">{t("spaceWeather.noEvents")}</p>;
  }

  const color = TAB_COLORS[eventType];

  return (
    <>
      <p className="sw-status-badge" aria-label={data.cached ? "cached" : "live"}>
        <span className={`sw-status-dot ${data.cached ? "sw-status-dot--cached" : "sw-status-dot--live"}`} />
        {data.stale
          ? t("error.staleData", { date: formatDateTime(data.fetched_at) })
          : data.cached
            ? `${t("common.cached")} · ${t("common.fetchedAt")} ${formatDateTime(data.fetched_at)}`
            : `${t("common.live")} · ${t("common.fetchedAt")} ${formatDateTime(data.fetched_at)}`}
      </p>

      <ActivityTimeline events={data.data} start={start} end={end} color={color} />

      <div className="sw-card-grid" role="list">
        {data.data.map((event) => (
          <div key={event.id} role="listitem">
            <EventCard event={event} />
          </div>
        ))}
      </div>
    </>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function SpaceWeatherPage() {
  const defaultEnd = todayIso();
  const defaultStart = addDaysIso(defaultEnd, -29);
  const [start, setStart] = useState(defaultStart);
  const [end, setEnd] = useState(defaultEnd);
  const [activeTab, setActiveTab] = useState<Tab>("FLR");
  const { t } = useTranslation();

  return (
    <div className="sw-page">
      <h1>{t("spaceWeather.title")}</h1>

      <div className="sw-controls">
        <div className="sw-date-row">
          <label className="sw-date-label" htmlFor="sw-start">
            {t("common.start")}
            <input
              id="sw-start"
              type="date"
              value={start}
              max={end}
              onChange={(e) => setStart(e.target.value)}
              className="sw-date-input"
            />
          </label>
          <span className="sw-date-arrow" aria-hidden="true">→</span>
          <label className="sw-date-label" htmlFor="sw-end">
            {t("common.end")}
            <input
              id="sw-end"
              type="date"
              value={end}
              min={start}
              onChange={(e) => setEnd(e.target.value)}
              className="sw-date-input"
            />
          </label>
        </div>
      </div>

      <div className="sw-tabs" role="tablist" aria-label={t("spaceWeather.title")}>
        {TABS.map((tab) => (
          <button
            key={tab.id}
            type="button"
            role="tab"
            aria-selected={activeTab === tab.id}
            aria-controls={`sw-panel-${tab.id}`}
            id={`sw-tab-${tab.id}`}
            onClick={() => setActiveTab(tab.id)}
            className={`sw-tab sw-tab--${tab.id}${activeTab === tab.id ? " sw-tab--active" : ""}`}
          >
            {TAB_ICONS[tab.id]}
            {t(tab.labelKey)}
          </button>
        ))}
      </div>

      {TABS.map((tab) => (
        <div
          key={tab.id}
          id={`sw-panel-${tab.id}`}
          role="tabpanel"
          aria-labelledby={`sw-tab-${tab.id}`}
          hidden={activeTab !== tab.id}
          className="sw-panel"
        >
          {activeTab === tab.id && (
            <TabPanel eventType={tab.id} start={start} end={end} />
          )}
        </div>
      ))}
    </div>
  );
}
