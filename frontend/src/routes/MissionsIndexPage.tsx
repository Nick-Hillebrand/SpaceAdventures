import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { fetchMissionIndex, type MissionIndexEntry } from "@/solar/mission";

type Status = "loading" | "ready" | "error";

export default function MissionsIndexPage() {
  const { t } = useTranslation();
  const [missions, setMissions] = useState<MissionIndexEntry[]>([]);
  const [status, setStatus] = useState<Status>("loading");

  useEffect(() => {
    let cancelled = false;
    fetchMissionIndex()
      .then((idx) => {
        if (cancelled) return;
        setMissions(idx.missions);
        setStatus("ready");
      })
      .catch(() => {
        if (!cancelled) setStatus("error");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div className="missions-index-page">
      <h1>{t("missions.indexTitle")}</h1>
      <p className="missions-index-page__subtitle">{t("missions.indexSubtitle")}</p>

      {status === "loading" && <p>{t("missions.loading")}</p>}
      {status === "error" && <p className="missions-index-page__error">{t("missions.loadError")}</p>}
      {status === "ready" && missions.length === 0 && <p>{t("missions.noMissions")}</p>}

      <ul className="missions-index-page__list">
        {missions.map((m) => (
          <li key={m.slug}>
            <Link to={`/missions/${m.slug}`}>{t(m.name_key)}</Link>
          </li>
        ))}
      </ul>
    </div>
  );
}
