import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { createRoverScene, type RoverScene } from "@/lib/roverScene";

const MODEL_URLS: Record<string, string> = {
  curiosity: "/models/curiosity.glb",
  perseverance: "/models/perseverance.glb",
  opportunity: "/models/mer.glb",
  spirit: "/models/mer.glb",
};

type Status = "loading" | "ready" | "error";

interface RoverViewerProps {
  rover: string;
}

export function RoverViewer({ rover }: RoverViewerProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const sceneRef = useRef<RoverScene | null>(null);
  const [status, setStatus] = useState<Status>("loading");
  const { t } = useTranslation();

  // P17: Guard containerRef.current inside useEffect
  useEffect(() => {
    if (!containerRef.current) return;
    const scene = createRoverScene(containerRef.current);
    sceneRef.current = scene;

    return () => {
      scene.dispose();
      sceneRef.current = null;
    };
  }, []);

  useEffect(() => {
    const scene = sceneRef.current;
    if (!scene) return;

    const url = MODEL_URLS[rover];
    if (!url) {
      setStatus("error");
      return;
    }

    let cancelled = false;
    setStatus("loading");
    scene
      .loadModel(url)
      .then(() => {
        if (!cancelled) setStatus("ready");
      })
      .catch(() => {
        if (!cancelled) setStatus("error");
      });

    return () => {
      cancelled = true;
    };
  }, [rover]);

  return (
    <div className="mars-rover-viewer">
      <div
        ref={containerRef}
        className="mars-rover-canvas"
        role="img"
        aria-label={t("mars.rover3dCanvasLabel", { rover })}
        data-testid="rover-3d-canvas"
      />
      {status === "loading" && (
        <p className="mars-rover-status" role="status">
          {t("mars.rover3dLoading")}
        </p>
      )}
      {status === "error" && (
        <p className="mars-rover-status mars-rover-status--error" role="alert">
          {t("mars.rover3dUnavailable")}
        </p>
      )}
      {status === "ready" && <p className="mars-rover-credit">{t("mars.rover3dCredit")}</p>}
    </div>
  );
}
