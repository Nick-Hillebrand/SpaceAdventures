import { useState, useCallback } from "react";
import { useTranslation } from "react-i18next";
import FullCalendar from "@fullcalendar/react";
import dayGridPlugin from "@fullcalendar/daygrid";
import { useLaunches } from "@/hooks/useLaunches";
import { LaunchCard } from "./LaunchCard";
import { ErrorBanner } from "@/components/ErrorBanner";
import { formatRelative } from "@/lib/dateTime";
import type { LaunchData } from "@/types/api";

type ViewMode = "grid" | "calendar";
type StatusFilter = "All" | "Go" | "TBD" | "Hold";

const VIEW_STORAGE_KEY = "space-adventures-launches-view";

function getInitialView(): ViewMode {
  try {
    const stored = localStorage.getItem(VIEW_STORAGE_KEY);
    if (stored === "calendar" || stored === "grid") return stored;
  } catch {
    /* localStorage unavailable */
  }
  return "grid";
}

function statusEventColor(abbrev: string): string {
  switch (abbrev) {
    case "Go":
      return "#22c55e";
    case "TBD":
      return "#f59e0b";
    case "Hold":
      return "#ef4444";
    default:
      return "#6366f1";
  }
}

export default function LaunchesPage() {
  const { data, isLoading, isError, error } = useLaunches();
  const { t } = useTranslation();
  const [view, setView] = useState<ViewMode>(getInitialView);
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("All");
  const [agencySearch, setAgencySearch] = useState("");
  const [selectedLaunch, setSelectedLaunch] = useState<LaunchData | null>(null);

  const switchView = useCallback((newView: ViewMode) => {
    setView(newView);
    try {
      localStorage.setItem(VIEW_STORAGE_KEY, newView);
    } catch {
      /* localStorage unavailable */
    }
  }, []);

  if (isLoading) {
    return (
      <div className="launches-page" data-testid="launches-page">
        <div className="launches-skeleton" role="status" aria-label={t("launches.loadingLaunches")}>
          <p>{t("launches.loadingLaunches")}</p>
        </div>
      </div>
    );
  }

  if (isError && error) {
    return (
      <div className="launches-page" data-testid="launches-page">
        <ErrorBanner
          titleKey="launches.failedToLoad"
          detail={error.message}
          variant="page"
        />
      </div>
    );
  }

  const launches = data?.data ?? [];
  const lastSyncedAt = data?.last_synced_at;

  const filtered = launches.filter((launch) => {
    const statusOk = statusFilter === "All" || launch.status_abbrev === statusFilter;
    const agencyOk =
      agencySearch.trim() === "" ||
      launch.agency_name.toLowerCase().includes(agencySearch.trim().toLowerCase());
    return statusOk && agencyOk;
  });

  const calendarEvents = filtered.map((launch) => ({
    id: launch.ll2_id,
    title: `${launch.agency_name}: ${launch.rocket_name}`,
    date: launch.net.slice(0, 10),
    backgroundColor: statusEventColor(launch.status_abbrev),
    borderColor: statusEventColor(launch.status_abbrev),
    extendedProps: launch,
  }));

  function handleCalendarEventClick(info: { event: { id: string; extendedProps: LaunchData & Record<string, unknown> } }) {
    const launch = filtered.find((l) => l.ll2_id === info.event.id);
    if (launch) setSelectedLaunch(launch);
  }

  const statusButtons: { filter: StatusFilter; labelKey: string; testId: string }[] = [
    { filter: "All", labelKey: "launches.filterAll", testId: "filter-status-all" },
    { filter: "Go", labelKey: "launches.filterGo", testId: "filter-status-go" },
    { filter: "TBD", labelKey: "launches.filterTbd", testId: "filter-status-tbd" },
    { filter: "Hold", labelKey: "launches.filterHold", testId: "filter-status-hold" },
  ];

  return (
    <div className="launches-page" data-testid="launches-page">
      <div className="launches-header">
        <h1>{t("launches.upcomingTitle")}</h1>

        <div className="launches-view-toggle">
          <button
            type="button"
            data-testid="view-grid"
            aria-pressed={view === "grid"}
            onClick={() => switchView("grid")}
          >
            {t("launches.grid")}
          </button>
          <button
            type="button"
            data-testid="view-calendar"
            aria-pressed={view === "calendar"}
            onClick={() => switchView("calendar")}
          >
            {t("launches.calendar")}
          </button>
        </div>
      </div>

      {lastSyncedAt && (
        <p className="launches-sync-time" data-testid="last-synced">
          {t("launches.lastUpdated", { time: formatRelative(lastSyncedAt) })}
        </p>
      )}

      {/* Filter bar */}
      <div className="launches-filters" data-testid="launches-filters">
        <div className="launches-status-filters">
          {statusButtons.map(({ filter, labelKey, testId }) => (
            <button
              key={filter}
              type="button"
              data-testid={testId}
              aria-pressed={statusFilter === filter}
              onClick={() => setStatusFilter(filter)}
            >
              {t(labelKey)}
            </button>
          ))}
        </div>
        <input
          type="text"
          placeholder={t("launches.searchAgency")}
          value={agencySearch}
          onChange={(e) => setAgencySearch(e.target.value)}
          data-testid="agency-search"
          aria-label={t("launches.filterByAgency")}
        />
      </div>

      {/* Main content */}
      {view === "grid" ? (
        <>
          {filtered.length === 0 ? (
            <div className="launches-empty" data-testid="launches-empty">
              <p>{t("launches.noFiltered")}</p>
            </div>
          ) : (
            <div className="launches-grid" data-testid="launches-grid">
              {filtered
                .slice()
                .sort((a, b) => new Date(a.net).getTime() - new Date(b.net).getTime())
                .map((launch) => (
                  <LaunchCard key={launch.ll2_id} launch={launch} />
                ))}
            </div>
          )}
        </>
      ) : (
        <div className="launches-calendar" data-testid="launches-calendar">
          <FullCalendar
            plugins={[dayGridPlugin]}
            initialView="dayGridMonth"
            editable={false}
            events={calendarEvents}
            eventClick={handleCalendarEventClick}
          />
        </div>
      )}

      {/* Slide-over drawer for calendar event clicks */}
      {selectedLaunch && (
        <div
          className="launches-drawer"
          data-testid="launch-drawer"
          role="dialog"
          aria-modal="true"
          aria-label={selectedLaunch.name}
        >
          <div className="launches-drawer__backdrop" onClick={() => setSelectedLaunch(null)} />
          <div className="launches-drawer__panel">
            <button
              type="button"
              onClick={() => setSelectedLaunch(null)}
              data-testid="drawer-close"
              aria-label={t("common.close")}
            >
              ✕
            </button>
            <LaunchCard launch={selectedLaunch} />
          </div>
        </div>
      )}
    </div>
  );
}
