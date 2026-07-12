// Shared mission-replay UI (Architecture/22, G3): mission picker, timeline
// scrubber with milestone ticks, and a milestone description card. Used by
// both entry points — the canonical /missions/:slug route and the in-context
// "Missions" panel on SolarSystemPage — driven by the same
// SolarSceneHandle.mission.load()/clear() the parent already mounted.
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { formatDateTime } from "@/lib/dateTime";
import type { MissionIndexEntry, MissionSpec } from "@/solar/mission";
import type { SolarSceneHandle } from "@/solar/scene";

const MIN_MULTIPLIER = 1;
const MAX_MULTIPLIER = 10_000;
const DEFAULT_SLIDER = 40;
const SECONDS_PER_DAY = 86_400;

function sliderToMultiplier(v: number): number {
  return MIN_MULTIPLIER * Math.pow(MAX_MULTIPLIER / MIN_MULTIPLIER, v / 100);
}

export interface MissionPanelProps {
  /** The already-mounted scene to drive; null while the engine is still mounting. */
  scene: SolarSceneHandle | null;
  simDate: Date;
  /** Catalogue for the picker. Ignored when showPicker is false. */
  missions: MissionIndexEntry[];
  activeSlug: string | null;
  /** The currently loaded mission, or null when no mission is active. */
  spec: MissionSpec | null;
  onSelectMission: (slug: string) => void;
  onClearMission: () => void;
  /** Solar-tab entry point shows the picker + exit button; canonical/embed pages don't. */
  showPicker?: boolean;
  /** Link to the canonical page, shown for sharing (solar-tab entry point only). */
  canonicalHref?: string;
}

export default function MissionPanel({
  scene,
  simDate,
  missions,
  activeSlug,
  spec,
  onSelectMission,
  onClearMission,
  showPicker = true,
  canonicalHref,
}: MissionPanelProps) {
  const { t } = useTranslation();
  const [paused, setPaused] = useState(false);
  const [slider, setSlider] = useState(DEFAULT_SLIDER);
  const [activeMilestone, setActiveMilestone] = useState<number | null>(null);

  // A newly loaded mission always starts playing from its own default speed;
  // stale milestone-card state from the previous mission must not carry over.
  useEffect(() => {
    setPaused(false);
    setSlider(DEFAULT_SLIDER);
    setActiveMilestone(null);
  }, [spec?.slug]);

  const multiplier = sliderToMultiplier(slider);

  useEffect(() => {
    if (!scene || !spec) return;
    scene.setSpeed(paused ? 0 : multiplier / SECONDS_PER_DAY);
  }, [scene, spec, paused, multiplier]);

  const t0 = spec ? Date.parse(spec.t0) : 0;
  const t1 = spec ? Date.parse(spec.t1) : 0;
  const simMs = spec ? Math.min(Math.max(simDate.getTime(), t0), t1) : t0;

  function handleScrub(value: number) {
    setActiveMilestone(null);
    scene?.setDate(new Date(value));
  }

  function handleMilestoneClick(index: number, atMs: number) {
    setActiveMilestone(index);
    scene?.setDate(new Date(atMs));
  }

  const activeMilestoneData = spec && activeMilestone !== null ? spec.milestones[activeMilestone] : null;

  return (
    <div className="mission-panel">
      {showPicker && (
        <div className="mission-panel__picker">
          <h2>{t("missions.pickerTitle")}</h2>
          {missions.length === 0 && <p className="mission-panel__empty">{t("missions.noMissions")}</p>}
          <ul className="mission-panel__list">
            {missions.map((m) => (
              <li key={m.slug}>
                <button
                  type="button"
                  className={`mission-panel__pick${activeSlug === m.slug ? " mission-panel__pick--active" : ""}`}
                  aria-pressed={activeSlug === m.slug}
                  onClick={() => onSelectMission(m.slug)}
                >
                  {t(m.name_key)}
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}

      {spec && (
        <div className="mission-panel__active" aria-label={t(spec.name_key)}>
          <div className="mission-panel__head">
            <h2>{t(spec.name_key)}</h2>
            {showPicker && (
              <button type="button" className="mission-panel__exit" onClick={onClearMission}>
                {t("missions.exit")}
              </button>
            )}
          </div>

          <div className="mission-panel__transport">
            <button
              type="button"
              className="mission-panel__play"
              aria-pressed={paused}
              onClick={() => setPaused((p) => !p)}
            >
              {paused ? `▶ ${t("missions.play")}` : `⏸ ${t("missions.pause")}`}
            </button>
            <label className="mission-panel__speed">
              {t("missions.speed")}
              <input
                type="range"
                min={0}
                max={100}
                value={slider}
                aria-label={t("missions.speed")}
                onChange={(e) => setSlider(Number(e.target.value))}
              />
              <span className="mission-panel__speed-value">
                {t("missions.speedValue", { n: Math.round(multiplier) })}
              </span>
            </label>
          </div>

          <div className="mission-panel__scrubber-wrap">
            <input
              type="range"
              className="mission-panel__scrubber"
              min={t0}
              max={t1}
              step={1000}
              value={simMs}
              aria-label={t("missions.scrubberLabel")}
              onChange={(e) => handleScrub(Number(e.target.value))}
            />
            <div className="mission-panel__ticks">
              {spec.milestones.map((m, i) => {
                const atMs = Date.parse(m.t);
                const pct = t1 > t0 ? ((atMs - t0) / (t1 - t0)) * 100 : 0;
                return (
                  <button
                    key={`${m.t}-${i}`}
                    type="button"
                    className={`mission-panel__tick${activeMilestone === i ? " mission-panel__tick--active" : ""}`}
                    style={{ left: `${pct}%` }}
                    aria-label={t(m.key)}
                    onClick={() => handleMilestoneClick(i, atMs)}
                  />
                );
              })}
            </div>
          </div>

          <p className="mission-panel__time">{formatDateTime(new Date(simMs).toISOString())}</p>

          {activeMilestoneData && (
            <div className="mission-panel__milestone-card">
              <p>{t(activeMilestoneData.key)}</p>
            </div>
          )}

          {canonicalHref && (
            <a className="mission-panel__canonical" href={canonicalHref}>
              {t("missions.viewFull")}
            </a>
          )}
        </div>
      )}
    </div>
  );
}
