import { useEffect, useRef, useCallback } from "react";
import type { NeoData } from "@/types/api";

interface Props {
  neos: NeoData[];
  selectedId: string | null;
  onSelect: (id: string) => void;
}

interface OrbitParams {
  a: number;      // semi-major axis in AU
  e: number;      // eccentricity
  omega: number;  // argument of perihelion (rad)
  M0: number;     // initial mean anomaly (rad)
  T: number;      // orbital period in sim years
}

interface Star {
  x: number;
  y: number;
  r: number;
  a: number;
  twinkle: number;
}

const ORBIT_PX = 115;       // pixels per AU
const SIM_YEAR_SECS = 14;   // 14 real seconds = 1 sim year (Earth completes one orbit)
const TRAIL_LEN = 55;

function seedRandom(id: string): () => number {
  let s = 0;
  for (let i = 0; i < id.length; i++) {
    s = Math.imul(s * 31 + id.charCodeAt(i), 1664525) + 1013904223;
    s >>>= 0;
  }
  return () => {
    s = Math.imul(s, 1664525) + 1013904223;
    s >>>= 0;
    return s / 4294967296;
  };
}

function solveKepler(M: number, e: number): number {
  let E = M;
  for (let i = 0; i < 6; i++) {
    E -= (E - e * Math.sin(E) - M) / (1 - e * Math.cos(E));
  }
  return E;
}

function getOrbitParams(neo: NeoData): OrbitParams {
  const rng = seedRandom(neo.id);
  const a = 0.8 + rng() * 1.5;
  const e = 0.12 + rng() * 0.58;
  const omega = rng() * 2 * Math.PI;
  const M0 = rng() * 2 * Math.PI;
  const T = Math.pow(a, 1.5);
  return { a, e, omega, M0, T };
}

function getBodyPos(params: OrbitParams, t_secs: number): { x: number; y: number } {
  const t_sim = t_secs / SIM_YEAR_SECS;
  const n = (2 * Math.PI) / params.T;
  let M = (params.M0 + n * t_sim) % (2 * Math.PI);
  if (M < 0) M += 2 * Math.PI;
  const E = solveKepler(M, params.e);
  const xOrb = params.a * (Math.cos(E) - params.e);
  const yOrb = params.a * Math.sqrt(1 - params.e * params.e) * Math.sin(E);
  const cosW = Math.cos(params.omega);
  const sinW = Math.sin(params.omega);
  return {
    x: xOrb * cosW - yOrb * sinW,
    y: xOrb * sinW + yOrb * cosW,
  };
}

export function NeoOrbitSimulation({ neos, selectedId, onSelect }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const animRef = useRef<number>(0);
  const startTimeRef = useRef<number>(Date.now());
  const neosRef = useRef(neos);
  const selectedIdRef = useRef(selectedId);
  const orbitsRef = useRef<Map<string, OrbitParams>>(new Map());
  const trailsRef = useRef<Map<string, { x: number; y: number }[]>>(new Map());
  const starsRef = useRef<Star[]>([]);

  useEffect(() => { neosRef.current = neos; }, [neos]);
  useEffect(() => { selectedIdRef.current = selectedId; }, [selectedId]);

  useEffect(() => {
    const map = new Map<string, OrbitParams>();
    const tmap = new Map<string, { x: number; y: number }[]>();
    for (const neo of neos) {
      map.set(neo.id, getOrbitParams(neo));
      tmap.set(neo.id, []);
    }
    orbitsRef.current = map;
    trailsRef.current = tmap;
  }, [neos]);

  const handleClick = useCallback((e: React.MouseEvent<HTMLCanvasElement>) => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const rect = canvas.getBoundingClientRect();
    const scaleX = canvas.width / rect.width;
    const scaleY = canvas.height / rect.height;
    const mx = (e.clientX - rect.left) * scaleX;
    const my = (e.clientY - rect.top) * scaleY;
    const cx = canvas.width / 2;
    const cy = canvas.height / 2;
    const t = (Date.now() - startTimeRef.current) / 1000;

    let closest: { id: string; dist: number } | null = null;
    for (const neo of neosRef.current) {
      const params = orbitsRef.current.get(neo.id);
      if (!params) continue;
      const pos = getBodyPos(params, t);
      const px = cx + pos.x * ORBIT_PX;
      const py = cy + pos.y * ORBIT_PX;
      const dist = Math.hypot(mx - px, my - py);
      if (!closest || dist < closest.dist) closest = { id: neo.id, dist };
    }
    if (closest && closest.dist < 14) onSelect(closest.id);
  }, [onSelect]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const W = canvas.width;
    const H = canvas.height;

    const starRng = seedRandom("neo-stars-v2");
    starsRef.current = Array.from({ length: 200 }, () => ({
      x: starRng() * W,
      y: starRng() * H,
      r: 0.3 + starRng() * 1.4,
      a: 0.25 + starRng() * 0.65,
      twinkle: starRng() * Math.PI * 2,
    }));

    function draw() {
      if (!canvas || !ctx) return;
      const t = (Date.now() - startTimeRef.current) / 1000;
      const cx = W / 2;
      const cy = H / 2;
      const currentNeos = neosRef.current;
      const currentSelected = selectedIdRef.current;

      // Background
      ctx.fillStyle = "#010409";
      ctx.fillRect(0, 0, W, H);

      // Nebula glow background (subtle)
      const nebula1 = ctx.createRadialGradient(W * 0.2, H * 0.3, 0, W * 0.2, H * 0.3, W * 0.4);
      nebula1.addColorStop(0, "rgba(30, 10, 60, 0.25)");
      nebula1.addColorStop(1, "transparent");
      ctx.fillStyle = nebula1;
      ctx.fillRect(0, 0, W, H);

      const nebula2 = ctx.createRadialGradient(W * 0.8, H * 0.7, 0, W * 0.8, H * 0.7, W * 0.35);
      nebula2.addColorStop(0, "rgba(5, 20, 50, 0.3)");
      nebula2.addColorStop(1, "transparent");
      ctx.fillStyle = nebula2;
      ctx.fillRect(0, 0, W, H);

      // Stars with subtle twinkle
      for (const star of starsRef.current) {
        const alpha = star.a * (0.7 + 0.3 * Math.sin(t * 1.5 + star.twinkle));
        ctx.globalAlpha = alpha;
        ctx.fillStyle = "#e2e8f8";
        ctx.beginPath();
        ctx.arc(star.x, star.y, star.r, 0, 2 * Math.PI);
        ctx.fill();
      }
      ctx.globalAlpha = 1;

      // Earth orbit ring (1 AU)
      ctx.beginPath();
      ctx.arc(cx, cy, ORBIT_PX, 0, 2 * Math.PI);
      ctx.strokeStyle = "rgba(96, 165, 250, 0.18)";
      ctx.lineWidth = 1;
      ctx.setLineDash([5, 7]);
      ctx.stroke();
      ctx.setLineDash([]);

      // NEO orbit paths
      for (const neo of currentNeos) {
        const params = orbitsRef.current.get(neo.id);
        if (!params) continue;
        const isSelected = neo.id === currentSelected;
        const b = params.a * Math.sqrt(1 - params.e * params.e);
        const c = params.a * params.e;

        ctx.beginPath();
        ctx.ellipse(
          cx - c * Math.cos(params.omega) * ORBIT_PX,
          cy - c * Math.sin(params.omega) * ORBIT_PX,
          params.a * ORBIT_PX,
          b * ORBIT_PX,
          params.omega,
          0, 2 * Math.PI
        );
        if (neo.is_potentially_hazardous) {
          ctx.strokeStyle = isSelected
            ? "rgba(251, 113, 113, 0.55)"
            : "rgba(251, 113, 113, 0.1)";
        } else {
          ctx.strokeStyle = isSelected
            ? "rgba(147, 197, 253, 0.55)"
            : "rgba(147, 197, 253, 0.09)";
        }
        ctx.lineWidth = isSelected ? 1.5 : 0.7;
        ctx.stroke();
      }

      // Sun outer glow
      const sunHalo = ctx.createRadialGradient(cx, cy, 12, cx, cy, 70);
      sunHalo.addColorStop(0, "rgba(251, 191, 36, 0.35)");
      sunHalo.addColorStop(0.4, "rgba(251, 100, 20, 0.12)");
      sunHalo.addColorStop(1, "transparent");
      ctx.fillStyle = sunHalo;
      ctx.beginPath();
      ctx.arc(cx, cy, 70, 0, 2 * Math.PI);
      ctx.fill();

      // Sun pulsing corona
      const pulse = 0.85 + 0.15 * Math.sin(t * 1.8);
      const sunCorona = ctx.createRadialGradient(cx, cy, 8, cx, cy, 34 * pulse);
      sunCorona.addColorStop(0, "rgba(255, 220, 80, 0.2)");
      sunCorona.addColorStop(1, "transparent");
      ctx.fillStyle = sunCorona;
      ctx.beginPath();
      ctx.arc(cx, cy, 34 * pulse, 0, 2 * Math.PI);
      ctx.fill();

      // Sun body
      const sunGrad = ctx.createRadialGradient(cx - 5, cy - 5, 1, cx, cy, 15);
      sunGrad.addColorStop(0, "#fffde7");
      sunGrad.addColorStop(0.35, "#ffd700");
      sunGrad.addColorStop(0.75, "#ff9800");
      sunGrad.addColorStop(1, "#e65100");
      ctx.fillStyle = sunGrad;
      ctx.beginPath();
      ctx.arc(cx, cy, 15, 0, 2 * Math.PI);
      ctx.fill();

      // Earth
      const earthAngle = (t / SIM_YEAR_SECS) * 2 * Math.PI;
      const ex = cx + Math.cos(earthAngle) * ORBIT_PX;
      const ey = cy + Math.sin(earthAngle) * ORBIT_PX;

      const earthAtmo = ctx.createRadialGradient(ex, ey, 4, ex, ey, 14);
      earthAtmo.addColorStop(0, "rgba(96, 165, 250, 0.3)");
      earthAtmo.addColorStop(0.6, "rgba(59, 130, 246, 0.12)");
      earthAtmo.addColorStop(1, "transparent");
      ctx.fillStyle = earthAtmo;
      ctx.beginPath();
      ctx.arc(ex, ey, 14, 0, 2 * Math.PI);
      ctx.fill();

      const earthGrad = ctx.createRadialGradient(ex - 2, ey - 2, 0.5, ex, ey, 5.5);
      earthGrad.addColorStop(0, "#bfdbfe");
      earthGrad.addColorStop(0.45, "#3b82f6");
      earthGrad.addColorStop(1, "#1e3a8a");
      ctx.fillStyle = earthGrad;
      ctx.beginPath();
      ctx.arc(ex, ey, 5.5, 0, 2 * Math.PI);
      ctx.fill();

      // NEO trails and bodies
      for (const neo of currentNeos) {
        const params = orbitsRef.current.get(neo.id);
        if (!params) continue;
        const pos = getBodyPos(params, t);
        const px = cx + pos.x * ORBIT_PX;
        const py = cy + pos.y * ORBIT_PX;
        const isSelected = neo.id === currentSelected;
        const isHazardous = neo.is_potentially_hazardous;

        // Trail
        const trail = trailsRef.current.get(neo.id) ?? [];
        trail.push({ x: px, y: py });
        if (trail.length > TRAIL_LEN) trail.shift();
        trailsRef.current.set(neo.id, trail);

        if (trail.length > 2) {
          for (let i = 2; i < trail.length; i++) {
            const frac = i / trail.length;
            const alpha = frac * frac * (isSelected ? 0.7 : 0.22);
            ctx.strokeStyle = isHazardous
              ? `rgba(252, 100, 100, ${alpha})`
              : `rgba(147, 197, 253, ${alpha})`;
            ctx.lineWidth = isSelected ? 1.4 : 0.7;
            ctx.beginPath();
            ctx.moveTo(trail[i - 1].x, trail[i - 1].y);
            ctx.lineTo(trail[i].x, trail[i].y);
            ctx.stroke();
          }
        }

        // Glow for selected
        if (isSelected) {
          const glowR = ctx.createRadialGradient(px, py, 0, px, py, 18);
          glowR.addColorStop(0, isHazardous ? "rgba(252, 100, 100, 0.5)" : "rgba(147, 197, 253, 0.5)");
          glowR.addColorStop(1, "transparent");
          ctx.fillStyle = glowR;
          ctx.beginPath();
          ctx.arc(px, py, 18, 0, 2 * Math.PI);
          ctx.fill();
        }

        // Body
        const diam = neo.estimated_diameter_max_km ?? 0.05;
        const bodyR = Math.max(2.5, Math.min(5.5, 2.5 + Math.log1p(diam) * 1.4));
        const bodyColor = isHazardous
          ? (isSelected ? "#fca5a5" : "#f87171")
          : (isSelected ? "#bfdbfe" : "#93c5fd");
        ctx.fillStyle = bodyColor;
        ctx.beginPath();
        ctx.arc(px, py, isSelected ? bodyR + 1.2 : bodyR, 0, 2 * Math.PI);
        ctx.fill();
      }

      // Labels
      ctx.font = "bold 11px system-ui, -apple-system, sans-serif";
      ctx.fillStyle = "rgba(251, 191, 36, 0.75)";
      ctx.fillText("Sun", cx + 18, cy + 4);

      ctx.fillStyle = "rgba(147, 197, 253, 0.75)";
      ctx.fillText("Earth", ex + 9, ey + 4);

      // Selected NEO label
      if (currentSelected) {
        const neo = currentNeos.find((n) => n.id === currentSelected);
        const params = orbitsRef.current.get(currentSelected);
        if (neo && params) {
          const pos = getBodyPos(params, t);
          const px = cx + pos.x * ORBIT_PX;
          const py = cy + pos.y * ORBIT_PX;
          ctx.font = "11px system-ui, -apple-system, sans-serif";
          ctx.fillStyle = "rgba(255,255,255,0.92)";
          ctx.fillText(neo.name, px + 7, py - 6);
        }
      }

      animRef.current = requestAnimationFrame(draw);
    }

    animRef.current = requestAnimationFrame(draw);
    return () => { cancelAnimationFrame(animRef.current); };
  }, []); // runs once; reads via refs

  return (
    <div className="neo-sim-wrapper">
      <canvas
        ref={canvasRef}
        width={800}
        height={440}
        className="neo-sim-canvas"
        onClick={handleClick}
        role="img"
        aria-label="Near-Earth Object orbital simulation around the Sun"
      />
      <div className="neo-sim-legend">
        <span className="neo-sim-legend-item">
          <span className="neo-sim-legend-dot" style={{ background: "#ffd700" }} />
          Sun
        </span>
        <span className="neo-sim-legend-item">
          <span className="neo-sim-legend-dot" style={{ background: "#3b82f6" }} />
          Earth (1 AU)
        </span>
        <span className="neo-sim-legend-item">
          <span className="neo-sim-legend-dot" style={{ background: "#93c5fd" }} />
          Safe NEO
        </span>
        <span className="neo-sim-legend-item">
          <span className="neo-sim-legend-dot neo-sim-legend-dot--hazard" style={{ background: "#f87171" }} />
          Potentially Hazardous
        </span>
        <span className="neo-sim-legend-hint">Click an object to select</span>
      </div>
    </div>
  );
}
