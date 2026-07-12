import { useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import MissionPanel from "@/components/MissionPanel";
import { fetchMissionSpec, type MissionSpec } from "@/solar/mission";
import { createSolarScene, type SolarSceneHandle } from "@/solar/scene";

type Status = "loading" | "ready" | "error";

interface MissionPageProps {
  /** Chrome-less variant for /missions/:slug/embed — no back-link, keeps the attribution line. */
  embed?: boolean;
}

const NOOP_SELECT_MISSION = () => {};
const NOOP_CLEAR_MISSION = () => {};

export default function MissionPage({ embed = false }: MissionPageProps) {
  const { slug = "" } = useParams();
  const { t, i18n } = useTranslation();
  const containerRef = useRef<HTMLDivElement>(null);
  const getLabelRef = useRef((id: string) => t(`solar.bodies.${id}`, { defaultValue: id }));
  getLabelRef.current = (id: string) => t(`solar.bodies.${id}`, { defaultValue: id });

  const [scene, setScene] = useState<SolarSceneHandle | null>(null);
  const [simDate, setSimDate] = useState<Date>(() => new Date());
  const [spec, setSpec] = useState<MissionSpec | null>(null);
  const [status, setStatus] = useState<Status>("loading");

  // Declared before the scene-creation effect below so its cleanup
  // (scene.mission.clear()) runs on unmount before handle.dispose() does —
  // React fires cleanups in declaration order, and clearing a mission
  // against an already-disposed scene is a no-op that skips the intended
  // camera/clock restoration.
  useEffect(() => {
    if (!scene || !spec) return;
    scene.mission.load(spec);
    return () => scene.mission.clear();
  }, [scene, spec]);

  useEffect(() => {
    if (!containerRef.current) return;
    const handle = createSolarScene(containerRef.current, {
      getLabel: (id) => getLabelRef.current(id),
      onSelect: () => {},
      onDateTick: setSimDate,
      initialScaleMode: "true",
    });
    setScene(handle);
    return () => {
      setScene(null);
      handle.dispose();
    };
  }, []);

  useEffect(() => {
    scene?.refreshLabels();
  }, [scene, i18n.resolvedLanguage]);

  useEffect(() => {
    let cancelled = false;
    setStatus("loading");
    setSpec(null);
    fetchMissionSpec(slug)
      .then((data) => {
        if (cancelled) return;
        setSpec(data);
        setStatus("ready");
      })
      .catch(() => {
        if (!cancelled) setStatus("error");
      });
    return () => {
      cancelled = true;
    };
  }, [slug]);

  return (
    <div className={embed ? "mission-embed-page" : "mission-page"}>
      {!embed && (
        <div className="solar-header">
          <h1>{spec ? t(spec.name_key) : t("missions.pickerTitle")}</h1>
          <Link to="/missions" className="mission-page__back">
            {t("missions.backToMissions")}
          </Link>
        </div>
      )}

      <div className="solar-stage">
        <div
          ref={containerRef}
          className="solar-canvas"
          data-testid="solar-canvas"
          aria-label={t("missions.canvasLabel")}
        />
      </div>

      {status === "loading" && <p className="mission-page__status">{t("missions.loading")}</p>}
      {status === "error" && (
        <p className="mission-page__status mission-page__status--error">{t("missions.loadError")}</p>
      )}

      <MissionPanel
        scene={scene}
        simDate={simDate}
        missions={[]}
        activeSlug={spec?.slug ?? null}
        spec={spec}
        onSelectMission={NOOP_SELECT_MISSION}
        onClearMission={NOOP_CLEAR_MISSION}
        showPicker={false}
      />

      {embed && (
        <p className="mission-embed-page__attribution">
          <a href={`/missions/${slug}`} target="_blank" rel="noreferrer">
            {t("missions.embedAttribution")}
          </a>
        </p>
      )}
    </div>
  );
}
