import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import MissionPanel from "@/components/MissionPanel";
import { PLANETS, SUN, type MoonData, type PlanetData } from "@/solar/data";
import { fetchMissionIndex, fetchMissionSpec, type MissionIndexEntry, type MissionSpec } from "@/solar/mission";
import { createSolarScene, type ScaleMode, type SolarSceneHandle } from "@/solar/scene";

const MIN_SPEED = 0.01; // days per second
const MAX_SPEED = 365;
const DEFAULT_SLIDER = 55;

function sliderToSpeed(v: number): number {
  return MIN_SPEED * Math.pow(MAX_SPEED / MIN_SPEED, v / 100);
}

interface MoonSelection {
  moon: MoonData;
  parent: PlanetData;
}

function findMoon(id: string): MoonSelection | null {
  for (const planet of PLANETS) {
    const moon = planet.moons.find((m) => m.id === id);
    if (moon) return { moon, parent: planet };
  }
  return null;
}

export default function SolarSystemPage() {
  const { t, i18n } = useTranslation();
  const containerRef = useRef<HTMLDivElement>(null);
  const sceneRef = useRef<SolarSceneHandle | null>(null);

  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [simDate, setSimDate] = useState<Date>(() => new Date());
  const [paused, setPaused] = useState(false);
  const [slider, setSlider] = useState(DEFAULT_SLIDER);
  const [scaleMode, setScaleMode] = useState<ScaleMode>("visible");

  const [missionsOpen, setMissionsOpen] = useState(false);
  const [missionIndex, setMissionIndex] = useState<MissionIndexEntry[]>([]);
  const [missionSpec, setMissionSpec] = useState<MissionSpec | null>(null);
  const [missionSlug, setMissionSlug] = useState<string | null>(null);
  const [missionError, setMissionError] = useState(false);

  const speed = sliderToSpeed(slider);

  const numberFmt = useMemo(
    () => new Intl.NumberFormat(i18n.resolvedLanguage ?? "en", { maximumFractionDigits: 1 }),
    [i18n.resolvedLanguage],
  );

  const getLabel = useCallback(
    (id: string) => t(`solar.bodies.${id}`, { defaultValue: id }),
    [t],
  );
  const getLabelRef = useRef(getLabel);
  getLabelRef.current = getLabel;

  useEffect(() => {
    if (!containerRef.current) return;
    const scene = createSolarScene(containerRef.current, {
      getLabel: (id) => getLabelRef.current(id),
      onSelect: setSelectedId,
      onDateTick: setSimDate,
      initialSpeed: sliderToSpeed(DEFAULT_SLIDER),
    });
    sceneRef.current = scene;
    return () => {
      sceneRef.current = null;
      scene.dispose();
    };
  }, []);

  useEffect(() => {
    sceneRef.current?.refreshLabels();
  }, [i18n.resolvedLanguage]);

  useEffect(() => {
    // While a mission is loaded, MissionPanel owns the sim clock's speed —
    // don't fight it. Re-runs on missionSpec becoming null, restoring the
    // main transport's own speed.
    if (missionSpec) return;
    sceneRef.current?.setSpeed(paused ? 0 : speed);
  }, [paused, speed, missionSpec]);

  useEffect(() => {
    if (!missionsOpen || missionIndex.length > 0) return;
    let cancelled = false;
    fetchMissionIndex()
      .then((idx) => {
        if (!cancelled) setMissionIndex(idx.missions);
      })
      .catch(() => {
        if (!cancelled) setMissionError(true);
      });
    return () => {
      cancelled = true;
    };
  }, [missionsOpen, missionIndex.length]);

  async function handleSelectMission(slug: string) {
    setMissionError(false);
    try {
      const spec = await fetchMissionSpec(slug);
      sceneRef.current?.mission.load(spec);
      setMissionSpec(spec);
      setMissionSlug(slug);
      setMissionError(false);
    } catch {
      setMissionError(true);
    }
  }

  function handleClearMission() {
    sceneRef.current?.mission.clear();
    setMissionSpec(null);
    setMissionSlug(null);
  }

  function handleScaleMode(mode: ScaleMode) {
    setScaleMode(mode);
    sceneRef.current?.setScaleMode(mode);
  }

  function handleNow() {
    sceneRef.current?.setDate(new Date());
  }

  function handleDateInput(value: string) {
    if (!value) return;
    const next = new Date(`${value}T12:00:00Z`);
    if (!Number.isNaN(next.getTime())) sceneRef.current?.setDate(next);
  }

  function handleSelect(id: string | null) {
    sceneRef.current?.select(id);
  }

  const selectedPlanet =
    selectedId === "sun" ? null : PLANETS.find((p) => p.id === selectedId) ?? null;
  const selectedMoon = !selectedPlanet && selectedId && selectedId !== "sun" ? findMoon(selectedId) : null;
  const sunSelected = selectedId === "sun";

  const speedLabel =
    speed >= 1
      ? t("solar.speedDays", { n: numberFmt.format(speed) })
      : t("solar.speedHours", { n: numberFmt.format(speed * 24) });

  const dateInputValue = simDate.toISOString().slice(0, 10);

  function formatYears(days: number): string {
    return days >= 365
      ? t("solar.factYears", { n: numberFmt.format(days / 365.25) })
      : t("solar.factDays", { n: numberFmt.format(days) });
  }

  function formatRotation(hours: number): string {
    const abs = Math.abs(hours);
    const label =
      abs >= 48
        ? t("solar.factDays", { n: numberFmt.format(abs / 24) })
        : t("solar.factHours", { n: numberFmt.format(abs) });
    return hours < 0 ? `${label} ${t("solar.retrograde")}` : label;
  }

  return (
    <div className="solar-page">
      <div className="solar-header">
        <h1>{t("solar.title")}</h1>
        <p className="solar-subtitle">{t("solar.subtitle")}</p>
        <button
          type="button"
          className="solar-btn"
          aria-pressed={missionsOpen}
          onClick={() => setMissionsOpen((o) => !o)}
        >
          {t("missions.toggle")}
        </button>
      </div>

      <div className="solar-stage">
        <div
          ref={containerRef}
          className="solar-canvas"
          data-testid="solar-canvas"
          aria-label={t("solar.canvasLabel")}
        />

        {(selectedPlanet || selectedMoon || sunSelected) && (
          <aside className="solar-info" aria-label={t("solar.infoPanelLabel")}>
            <div className="solar-info__head">
              <h2>{getLabel(selectedId!)}</h2>
              <button
                type="button"
                className="solar-info__close"
                aria-label={t("solar.close")}
                onClick={() => handleSelect(null)}
              >
                ×
              </button>
            </div>

            {(selectedPlanet || sunSelected) && (
              <>
                <p className="solar-info__type">
                  {sunSelected ? t("solar.typeStar") : t(`solar.type_${selectedPlanet!.type}`)}
                </p>
                <p className="solar-info__desc">{t(`solar.desc.${selectedId}`)}</p>
                <dl className="solar-facts">
                  <div>
                    <dt>{t("solar.factRadius")}</dt>
                    <dd>{numberFmt.format(sunSelected ? SUN.radiusKm : selectedPlanet!.radiusKm)} km</dd>
                  </div>
                  <div>
                    <dt>{t("solar.factMass")}</dt>
                    <dd>
                      {numberFmt.format(sunSelected ? SUN.facts.mass : selectedPlanet!.facts.mass)}
                      {" × 10²⁴ kg"}
                    </dd>
                  </div>
                  <div>
                    <dt>{t("solar.factGravity")}</dt>
                    <dd>{numberFmt.format((sunSelected ? SUN.facts : selectedPlanet!.facts).gravity)} m/s²</dd>
                  </div>
                  <div>
                    <dt>{t("solar.factTemp")}</dt>
                    <dd>{numberFmt.format((sunSelected ? SUN.facts : selectedPlanet!.facts).meanTempC)} °C</dd>
                  </div>
                  <div>
                    <dt>{t("solar.factDayLength")}</dt>
                    <dd>{formatRotation((sunSelected ? SUN.facts : selectedPlanet!.facts).rotationHours)}</dd>
                  </div>
                  {selectedPlanet && (
                    <>
                      <div>
                        <dt>{t("solar.factYearLength")}</dt>
                        <dd>{formatYears(selectedPlanet.orbit.periodDays)}</dd>
                      </div>
                      <div>
                        <dt>{t("solar.factDistance")}</dt>
                        <dd>{numberFmt.format(selectedPlanet.orbit.a)} AU</dd>
                      </div>
                      <div>
                        <dt>{t("solar.factAxialTilt")}</dt>
                        <dd>{numberFmt.format(selectedPlanet.facts.axialTiltDeg)}°</dd>
                      </div>
                      <div>
                        <dt>{t("solar.factMoons")}</dt>
                        <dd>{selectedPlanet.facts.moonCount}</dd>
                      </div>
                    </>
                  )}
                </dl>
                {selectedPlanet && selectedPlanet.moons.length > 0 && (
                  <div className="solar-info__moons">
                    <h3>{t("solar.majorMoons")}</h3>
                    <div className="solar-info__moon-chips">
                      {selectedPlanet.moons.map((moon) => (
                        <button
                          key={moon.id}
                          type="button"
                          className="solar-moon-chip"
                          onClick={() => handleSelect(moon.id)}
                        >
                          {getLabel(moon.id)}
                        </button>
                      ))}
                    </div>
                  </div>
                )}
              </>
            )}

            {selectedMoon && (
              <>
                <p className="solar-info__type">
                  {t("solar.typeMoon", { planet: getLabel(selectedMoon.parent.id) })}
                </p>
                <dl className="solar-facts">
                  <div>
                    <dt>{t("solar.factRadius")}</dt>
                    <dd>{numberFmt.format(selectedMoon.moon.radiusKm)} km</dd>
                  </div>
                  <div>
                    <dt>{t("solar.factOrbitRadius")}</dt>
                    <dd>{numberFmt.format(selectedMoon.moon.aThousandKm * 1000)} km</dd>
                  </div>
                  <div>
                    <dt>{t("solar.factOrbitPeriod")}</dt>
                    <dd>
                      {t("solar.factDays", { n: numberFmt.format(Math.abs(selectedMoon.moon.periodDays)) })}
                      {selectedMoon.moon.periodDays < 0 ? ` ${t("solar.retrograde")}` : ""}
                    </dd>
                  </div>
                </dl>
                <button
                  type="button"
                  className="solar-moon-chip"
                  onClick={() => handleSelect(selectedMoon.parent.id)}
                >
                  ← {getLabel(selectedMoon.parent.id)}
                </button>
              </>
            )}
          </aside>
        )}

        {missionsOpen && (
          <aside className="mission-dock" aria-label={t("missions.pickerTitle")}>
            <MissionPanel
              scene={sceneRef.current}
              simDate={simDate}
              missions={missionIndex}
              activeSlug={missionSlug}
              spec={missionSpec}
              onSelectMission={handleSelectMission}
              onClearMission={handleClearMission}
              showPicker
              canonicalHref={missionSlug ? `/missions/${missionSlug}` : undefined}
            />
            {missionError && <p className="mission-dock__error">{t("missions.loadError")}</p>}
          </aside>
        )}
      </div>

      <div className="solar-controls" aria-label={t("solar.controlsLabel")}>
        <div
          className="solar-controls__group"
          title={missionSpec ? t("missions.controlsLocked") : undefined}
        >
          <button
            type="button"
            className="solar-btn"
            aria-pressed={paused}
            disabled={!!missionSpec}
            onClick={() => setPaused((p) => !p)}
          >
            {paused ? `▶ ${t("solar.play")}` : `⏸ ${t("solar.pause")}`}
          </button>
          <label className="solar-speed">
            {t("solar.speed")}
            <input
              type="range"
              min={0}
              max={100}
              value={slider}
              aria-label={t("solar.speed")}
              disabled={!!missionSpec}
              onChange={(e) => setSlider(Number(e.target.value))}
            />
            <span className="solar-speed__value">{speedLabel}</span>
          </label>
        </div>

        <div
          className="solar-controls__group"
          title={missionSpec ? t("missions.controlsLocked") : undefined}
        >
          <label className="solar-date">
            {t("solar.date")}
            <input
              type="date"
              value={dateInputValue}
              disabled={!!missionSpec}
              onChange={(e) => handleDateInput(e.target.value)}
            />
          </label>
          <button type="button" className="solar-btn" disabled={!!missionSpec} onClick={handleNow}>
            {t("solar.now")}
          </button>
        </div>

        <div
          className="solar-controls__group"
          role="group"
          aria-label={t("solar.scaleLabel")}
          title={missionSpec ? t("missions.scaleLocked") : undefined}
        >
          <button
            type="button"
            className={`solar-btn solar-btn--toggle${scaleMode === "visible" ? " solar-btn--active" : ""}`}
            disabled={!!missionSpec}
            onClick={() => handleScaleMode("visible")}
          >
            {t("solar.scaleVisible")}
          </button>
          <button
            type="button"
            className={`solar-btn solar-btn--toggle${scaleMode === "true" ? " solar-btn--active" : ""}`}
            disabled={!!missionSpec}
            onClick={() => handleScaleMode("true")}
          >
            {t("solar.scaleTrue")}
          </button>
        </div>
      </div>

      <p className="solar-hint">{t("solar.hint")}</p>
      <p className="solar-credit">{t("solar.credit")}</p>
    </div>
  );
}
