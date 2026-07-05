import { useState } from "react";
import { useSpaceWeatherEvents } from "@/hooks/useSpaceWeather";
import { ErrorBanner } from "@/components/ErrorBanner";
import { formatDate, formatDateTime } from "@/lib/dateTime";
import type { SpaceWeatherEventData, SpaceWeatherEventType } from "@/types/api";

type Tab = SpaceWeatherEventType;

interface TabConfig {
  id: Tab;
  label: string;
}

const TABS: TabConfig[] = [
  { id: "FLR", label: "Solar Flares" },
  { id: "GST", label: "Geomagnetic Storms" },
  { id: "CME", label: "Coronal Mass Ejections" },
  { id: "SEP", label: "Solar Energetic Particles" },
  { id: "RBE", label: "Radiation Belt Enhancements" },
];

function todayIso(): string {
  const now = new Date();
  const y = now.getUTCFullYear();
  const m = String(now.getUTCMonth() + 1).padStart(2, "0");
  const d = String(now.getUTCDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
}

function addDaysIso(iso: string, days: number): string {
  const d = new Date(`${iso}T00:00:00Z`);
  if (Number.isNaN(d.getTime())) return iso;
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
}

function errorTitle(code: string): string {
  switch (code) {
    case "NO_INTERNET":
      return "No internet connection";
    case "NASA_UNAVAILABLE":
      return "NASA services are currently unavailable";
    case "NASA_AUTH_ERROR":
      return "Invalid NASA API Key";
    default:
      return "Something went wrong";
  }
}

function parseRaw(raw: string): Record<string, unknown> {
  try {
    return JSON.parse(raw) as Record<string, unknown>;
  } catch {
    return {};
  }
}

function renderTimestamp(value: unknown): string {
  if (typeof value === "string" && value.length >= 10) {
    try {
      return formatDateTime(value);
    } catch {
      return String(value);
    }
  }
  return value != null ? String(value) : "—";
}

function EventCard({ event }: { event: SpaceWeatherEventData }) {
  const data = parseRaw(event.raw_json);

  const timeFields: string[] = [];
  for (const key of ["beginTime", "startTime", "eventTime", "peakTime", "endTime"]) {
    const val = data[key];
    if (typeof val === "string" && val.length >= 10) {
      timeFields.push(key);
    }
  }

  const noteFields: [string, unknown][] = Object.entries(data).filter(
    ([k]) => !["beginTime", "startTime", "eventTime", "peakTime", "endTime"].includes(k) &&
             !k.endsWith("ID") && k !== "activityID"
  );

  return (
    <article className="sw-event-card" aria-label={`${event.event_type} event ${event.id}`}>
      <header className="sw-event-header">
        <span className="sw-event-type-badge">{event.event_type}</span>
        <time dateTime={event.start_date}>{formatDate(event.start_date)}</time>
      </header>
      <dl className="sw-event-details">
        {timeFields.map((field) => (
          <div key={field} className="sw-event-row">
            <dt>{field}</dt>
            <dd>{renderTimestamp(data[field])}</dd>
          </div>
        ))}
        {noteFields.slice(0, 4).map(([key, val]) => (
          <div key={key} className="sw-event-row">
            <dt>{key}</dt>
            <dd className="sw-event-value">
              {typeof val === "object" ? JSON.stringify(val) : String(val ?? "—")}
            </dd>
          </div>
        ))}
      </dl>
    </article>
  );
}

interface TabPanelProps {
  eventType: Tab;
  start: string;
  end: string;
}

function TabPanel({ eventType, start, end }: TabPanelProps) {
  const { data, isLoading, isError, error, refetch } = useSpaceWeatherEvents(
    eventType,
    start,
    end,
  );

  if (isLoading) {
    return <p role="status">Loading…</p>;
  }

  if (isError && error) {
    return (
      <ErrorBanner
        title={errorTitle(error.code)}
        detail={error.message}
        onRetry={() => refetch()}
        variant="section"
      />
    );
  }

  if (!data || data.data.length === 0) {
    return <p className="sw-empty">No events found in this date range.</p>;
  }

  return (
    <>
      <p className="sw-badge" aria-label={data.cached ? "cached" : "live"}>
        {data.stale
          ? `Showing cached data from ${formatDateTime(data.fetched_at)}`
          : data.cached
            ? `Served from cache · fetched ${formatDateTime(data.fetched_at)}`
            : `Live · fetched ${formatDateTime(data.fetched_at)}`}
      </p>
      <div className="sw-event-list" role="list">
        {data.data.map((event) => (
          <div key={event.id} role="listitem">
            <EventCard event={event} />
          </div>
        ))}
      </div>
    </>
  );
}

export default function SpaceWeatherPage() {
  const defaultEnd = todayIso();
  const defaultStart = addDaysIso(defaultEnd, -29);
  const [start, setStart] = useState<string>(defaultStart);
  const [end, setEnd] = useState<string>(defaultEnd);
  const [activeTab, setActiveTab] = useState<Tab>("FLR");

  return (
    <div className="sw-page">
      <h1>Space Weather</h1>

      <div className="sw-filters">
        <label htmlFor="sw-start">
          Start
          <input
            id="sw-start"
            type="date"
            value={start}
            max={end}
            onChange={(e) => setStart(e.target.value)}
          />
        </label>
        <label htmlFor="sw-end">
          End
          <input
            id="sw-end"
            type="date"
            value={end}
            min={start}
            onChange={(e) => setEnd(e.target.value)}
          />
        </label>
      </div>

      <div className="sw-tabs" role="tablist" aria-label="Space weather event types">
        {TABS.map((tab) => (
          <button
            key={tab.id}
            type="button"
            role="tab"
            aria-selected={activeTab === tab.id}
            aria-controls={`sw-panel-${tab.id}`}
            id={`sw-tab-${tab.id}`}
            onClick={() => setActiveTab(tab.id)}
            className={activeTab === tab.id ? "sw-tab sw-tab--active" : "sw-tab"}
          >
            {tab.label}
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
        >
          {activeTab === tab.id && (
            <TabPanel eventType={tab.id} start={start} end={end} />
          )}
        </div>
      ))}
    </div>
  );
}
