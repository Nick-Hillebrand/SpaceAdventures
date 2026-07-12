// Imperative three.js scene for the solar system simulator.
//
// Kept free of React so the page component can mount it in an effect (same
// pattern as globe.gl on the ISS page) and tests can mock this module.

import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { CSS2DObject, CSS2DRenderer } from "three/examples/jsm/renderers/CSS2DRenderer.js";
import { AU_KM, PLANETS, SUN, type MoonData, type PlanetData } from "./data";
import { daysSinceJ2000, heliocentricPosition, moonPosition, orbitPath } from "./orbits";
import type { MissionSpec } from "./mission";

export type ScaleMode = "visible" | "true";

export interface SolarSceneOptions {
  /** i18n lookup for body display names. */
  getLabel: (id: string) => string;
  onSelect: (id: string | null) => void;
  /** Called ~4×/s with the current simulation date. */
  onDateTick: (date: Date) => void;
  initialSpeed?: number;
  initialScaleMode?: ScaleMode;
}

export interface SolarSceneHandle {
  setSpeed(daysPerSecond: number): void;
  setScaleMode(mode: ScaleMode): void;
  setDate(date: Date): void;
  select(id: string | null): void;
  refreshLabels(): void;
  dispose(): void;
  mission: {
    /**
     * Loads a mission replay layer: trajectory polyline, craft marker, and
     * milestone ticks. Forces true-scale mode (locked until clear()), clamps
     * the sim clock to [t0, t1], applies Moon phase calibration if present,
     * and tweens the camera to frame the mission. Calling load() while a
     * mission is already active swaps the layer without disturbing the
     * pre-mission snapshot restored by clear().
     */
    load(spec: MissionSpec): void;
    /** Removes the mission layer and restores the prior clock, camera, and scale mode. */
    clear(): void;
  };
}

/** World units per AU in true-scale mode. */
const UNITS_PER_AU = 60;
const KM_TO_UNITS = UNITS_PER_AU / AU_KM;
/** Earth's display radius in visible mode; other bodies scale from it. */
const VISIBLE_EARTH_R = 3.2;
const VISIBLE_SUN_R = 10;

function visibleBodyRadius(radiusKm: number): number {
  return VISIBLE_EARTH_R * Math.pow(radiusKm / 6371, 0.4);
}

function visibleDistance(aAu: number): number {
  return 62 * Math.pow(aAu, 0.55);
}

interface MoonEntry {
  data: MoonData;
  group: THREE.Group;
  mesh: THREE.Mesh;
  label: CSS2DObject;
  labelEl: HTMLElement;
  phaseDeg: number;
}

interface BodyEntry {
  data: PlanetData;
  group: THREE.Group;
  tilt: THREE.Group;
  mesh: THREE.Mesh;
  ring?: THREE.Mesh;
  orbitLine: THREE.Line;
  label: CSS2DObject;
  labelEl: HTMLElement;
  moons: MoonEntry[];
}

export function createSolarScene(
  container: HTMLElement,
  options: SolarSceneOptions,
): SolarSceneHandle {
  const { getLabel, onSelect, onDateTick } = options;

  let scaleMode: ScaleMode = options.initialScaleMode ?? "visible";
  let daysPerSecond = options.initialSpeed ?? 2;
  let simDate = new Date();
  let selectedId: string | null = null;
  let disposed = false;

  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(
    50,
    Math.max(container.clientWidth, 1) / Math.max(container.clientHeight, 1),
    0.01,
    50_000,
  );
  camera.position.set(0, 170, 260);

  const renderer = new THREE.WebGLRenderer({ antialias: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  renderer.setSize(container.clientWidth || 800, container.clientHeight || 480);
  container.appendChild(renderer.domElement);

  const labelRenderer = new CSS2DRenderer();
  labelRenderer.setSize(container.clientWidth || 800, container.clientHeight || 480);
  labelRenderer.domElement.className = "solar-labels";
  container.appendChild(labelRenderer.domElement);

  const controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;
  controls.dampingFactor = 0.08;
  controls.minDistance = 0.05;
  controls.maxDistance = 4000;

  const textureLoader = new THREE.TextureLoader();
  const textures: THREE.Texture[] = [];
  function loadColorTexture(url: string): THREE.Texture {
    const tex = textureLoader.load(url);
    tex.colorSpace = THREE.SRGBColorSpace;
    tex.anisotropy = renderer.capabilities.getMaxAnisotropy();
    textures.push(tex);
    return tex;
  }

  // Lighting: the sun is the only real light source, plus a whisper of
  // ambient so night sides stay barely readable in a classroom setting.
  scene.add(new THREE.AmbientLight(0xffffff, 0.06));
  const sunLight = new THREE.PointLight(0xffffff, 2.2, 0, 0);
  scene.add(sunLight);

  // Star background.
  const skyGeo = new THREE.SphereGeometry(9000, 48, 24);
  const skyMat = new THREE.MeshBasicMaterial({
    map: loadColorTexture("/solar/2k_stars_milky_way.jpg"),
    side: THREE.BackSide,
    color: new THREE.Color(0x888888),
  });
  scene.add(new THREE.Mesh(skyGeo, skyMat));

  // Sun.
  const sunGroup = new THREE.Group();
  const sunMesh = new THREE.Mesh(
    new THREE.SphereGeometry(1, 64, 32),
    new THREE.MeshBasicMaterial({ map: loadColorTexture(SUN.texture) }),
  );
  sunMesh.name = "sun";
  sunGroup.add(sunMesh);
  const sunLabel = makeLabel("sun");
  sunGroup.add(sunLabel.object);
  scene.add(sunGroup);

  const bodies: BodyEntry[] = PLANETS.map((planet) => {
    const group = new THREE.Group();
    const tilt = new THREE.Group();
    tilt.rotation.z = THREE.MathUtils.degToRad(planet.facts.axialTiltDeg);
    group.add(tilt);

    const mesh = new THREE.Mesh(
      new THREE.SphereGeometry(1, 64, 32),
      new THREE.MeshStandardMaterial({
        map: loadColorTexture(planet.texture),
        roughness: 1,
        metalness: 0,
      }),
    );
    mesh.name = planet.id;
    tilt.add(mesh);

    let ring: THREE.Mesh | undefined;
    if (planet.ring) {
      const inner = planet.ring.innerKm / planet.radiusKm;
      const outer = planet.ring.outerKm / planet.radiusKm;
      const ringGeo = new THREE.RingGeometry(inner, outer, 128, 1);
      // Remap UVs so the ring texture strip runs inner→outer edge.
      const pos = ringGeo.attributes.position;
      const uv = ringGeo.attributes.uv;
      const mid = (inner + outer) / 2;
      for (let v = 0; v < pos.count; v++) {
        uv.setXY(v, Math.hypot(pos.getX(v), pos.getY(v)) < mid ? 0 : 1, 1);
      }
      const ringMat = new THREE.MeshLambertMaterial({
        side: THREE.DoubleSide,
        transparent: true,
      });
      if (planet.ring.texture) {
        ringMat.map = loadColorTexture(planet.ring.texture);
      } else {
        ringMat.color = new THREE.Color(planet.color);
        ringMat.opacity = 0.25;
      }
      ring = new THREE.Mesh(ringGeo, ringMat);
      ring.rotation.x = -Math.PI / 2;
      tilt.add(ring);
    }

    const orbitGeo = new THREE.BufferGeometry();
    const orbitMat = new THREE.LineBasicMaterial({
      color: new THREE.Color(planet.color),
      transparent: true,
      opacity: 0.4,
    });
    const orbitLine = new THREE.Line(orbitGeo, orbitMat);
    scene.add(orbitLine);

    const label = makeLabel(planet.id);
    group.add(label.object);

    const moons: MoonEntry[] = planet.moons.map((moon, idx) => {
      const moonGroup = new THREE.Group();
      const moonMesh = new THREE.Mesh(
        new THREE.SphereGeometry(1, 32, 16),
        new THREE.MeshStandardMaterial({
          map: moon.texture ? loadColorTexture(moon.texture) : null,
          color: moon.texture ? 0xffffff : new THREE.Color(moon.color),
          roughness: 1,
          metalness: 0,
        }),
      );
      moonMesh.name = moon.id;
      moonGroup.add(moonMesh);
      const moonLabel = makeLabel(moon.id, "solar-label solar-label--moon");
      moonGroup.add(moonLabel.object);
      group.add(moonGroup);
      return {
        data: moon,
        group: moonGroup,
        mesh: moonMesh,
        label: moonLabel.object,
        labelEl: moonLabel.el,
        // Spread starting phases so co-orbital rendering never stacks moons.
        phaseDeg: (idx * 137.5) % 360,
      };
    });

    scene.add(group);
    return { data: planet, group, tilt, mesh, ring, orbitLine, label: label.object, labelEl: label.el, moons };
  });

  function makeLabel(id: string, className = "solar-label"): { object: CSS2DObject; el: HTMLElement } {
    const el = document.createElement("button");
    el.type = "button";
    el.className = className;
    el.textContent = getLabel(id);
    el.addEventListener("pointerdown", (e) => e.stopPropagation());
    el.addEventListener("click", (e) => {
      e.stopPropagation();
      selectBody(id);
    });
    const object = new CSS2DObject(el);
    return { object, el };
  }

  // ---- scale-dependent layout -------------------------------------------

  function bodyDisplayRadius(radiusKm: number): number {
    return scaleMode === "visible" ? visibleBodyRadius(radiusKm) : radiusKm * KM_TO_UNITS;
  }

  function moonDisplayRadius(radiusKm: number): number {
    if (scaleMode === "true") return radiusKm * KM_TO_UNITS;
    return THREE.MathUtils.clamp(1.1 * Math.pow(radiusKm / 6371, 0.4), 0.35, 2.4);
  }

  function applyScaleMode() {
    const sunR = scaleMode === "visible" ? VISIBLE_SUN_R : SUN.radiusKm * KM_TO_UNITS;
    sunMesh.scale.setScalar(sunR);
    sunLabel.object.position.set(0, sunR * 1.25 + 1, 0);

    for (const body of bodies) {
      const r = bodyDisplayRadius(body.data.radiusKm);
      body.mesh.scale.setScalar(r);
      if (body.ring) body.ring.scale.setScalar(r);
      body.label.position.set(0, r * 1.5 + 0.8, 0);

      // Orbit line for the current mode.
      const scale = scaleMode === "true" ? UNITS_PER_AU : 1;
      const points = orbitPath(body.data.orbit).map((p) => {
        if (scaleMode === "true") {
          return new THREE.Vector3(p.x * scale, p.z * scale, -p.y * scale);
        }
        const d = visibleDistance(p.r);
        const f = d / p.r;
        return new THREE.Vector3(p.x * f, p.z * f, -p.y * f);
      });
      body.orbitLine.geometry.setFromPoints(points);

      body.moons.forEach((moon, idx) => {
        const mr = moonDisplayRadius(moon.data.radiusKm);
        moon.mesh.scale.setScalar(mr);
        moon.label.position.set(0, mr * 1.6 + 0.4, 0);
        moon.group.userData.dist =
          scaleMode === "true"
            ? moon.data.aThousandKm * 1000 * KM_TO_UNITS
            : r * 1.6 + 1.9 * (idx + 1);
      });
    }
  }

  // ---- simulation --------------------------------------------------------

  function updatePositions() {
    const days = daysSinceJ2000(simDate);

    for (const body of bodies) {
      const p = heliocentricPosition(body.data.orbit, days);
      if (scaleMode === "true") {
        body.group.position.set(p.x * UNITS_PER_AU, p.z * UNITS_PER_AU, -p.y * UNITS_PER_AU);
      } else {
        const f = visibleDistance(p.r) / p.r;
        body.group.position.set(p.x * f, p.z * f, -p.y * f);
      }

      // Deterministic self-rotation so scrubbing the date stays consistent.
      body.mesh.rotation.y = ((days * 24) / body.data.facts.rotationHours) * Math.PI * 2;

      for (const moon of body.moons) {
        const dist = moon.group.userData.dist as number;
        const m = moonPosition(1, moon.data.periodDays, days, moon.phaseDeg);
        moon.group.position.set(m.x * dist, 0, -m.y * dist);
      }
    }

    sunMesh.rotation.y = ((days * 24) / SUN.rotationHours) * Math.PI * 2;

    if (missionActive) updateMissionCraft();
  }

  // ---- selection & camera ------------------------------------------------

  const focusTween = { active: false, t: 0, fromPos: new THREE.Vector3(), toPos: new THREE.Vector3(), fromTarget: new THREE.Vector3(), toTarget: new THREE.Vector3() };

  function bodyWorldPosition(id: string, out: THREE.Vector3): boolean {
    if (id === "sun") {
      out.set(0, 0, 0);
      return true;
    }
    for (const body of bodies) {
      if (body.data.id === id) {
        body.group.getWorldPosition(out);
        return true;
      }
      for (const moon of body.moons) {
        if (moon.data.id === id) {
          moon.group.getWorldPosition(out);
          return true;
        }
      }
    }
    return false;
  }

  function displayRadiusOf(id: string): number {
    if (id === "sun") return scaleMode === "visible" ? VISIBLE_SUN_R : SUN.radiusKm * KM_TO_UNITS;
    for (const body of bodies) {
      if (body.data.id === id) return bodyDisplayRadius(body.data.radiusKm);
      for (const moon of body.moons) {
        if (moon.data.id === id) return moonDisplayRadius(moon.data.radiusKm);
      }
    }
    return 1;
  }

  function startFocusTween(toTarget: THREE.Vector3, toPos: THREE.Vector3) {
    focusTween.active = true;
    focusTween.t = 0;
    focusTween.fromPos.copy(camera.position);
    focusTween.toPos.copy(toPos);
    focusTween.fromTarget.copy(controls.target);
    focusTween.toTarget.copy(toTarget);
  }

  function focusOn(id: string | null) {
    const target = new THREE.Vector3();
    if (id === null || !bodyWorldPosition(id, target)) {
      const overview =
        scaleMode === "visible"
          ? new THREE.Vector3(0, 170, 260)
          : new THREE.Vector3(0, 900, 1400);
      startFocusTween(new THREE.Vector3(0, 0, 0), overview);
      return;
    }
    const r = displayRadiusOf(id);
    const dist = Math.max(r * 5.5, 0.4);
    const dir = camera.position.clone().sub(controls.target);
    if (dir.lengthSq() < 1e-6) dir.set(0, 0.5, 1);
    dir.normalize().multiplyScalar(dist);
    startFocusTween(target, target.clone().add(dir).add(new THREE.Vector3(0, dist * 0.25, 0)));
  }

  // ---- mission replay mode -------------------------------------------------
  //
  // A mode, not a second scene (Architecture/22-…, "Engine integration — one
  // engine, two entry points"): the mission layer is parented onto the
  // existing Earth group (geocentric) or the scene root (heliocentric) and
  // reuses the same true-scale coordinate mapping as the planets/moons.

  let missionActive = false;
  let missionWindow: { t0: number; t1: number } | null = null;
  let missionGroup: THREE.Group | null = null;
  let missionCraft: THREE.Mesh | null = null;
  let missionTimesMs: number[] = [];
  let missionPositions: THREE.Vector3[] = [];
  let missionMoonOverride: { entry: MoonEntry; priorPhaseDeg: number } | null = null;
  let savedBeforeMission: {
    scaleMode: ScaleMode;
    simDate: Date;
    daysPerSecond: number;
    cameraPos: THREE.Vector3;
    cameraTarget: THREE.Vector3;
  } | null = null;

  function missionPointToVector(p: { x: number; y: number; z: number }): THREE.Vector3 {
    return new THREE.Vector3(p.x * KM_TO_UNITS, p.z * KM_TO_UNITS, -p.y * KM_TO_UNITS);
  }

  function missionPositionAtMs(ms: number): THREE.Vector3 | null {
    if (missionPositions.length === 0) return null;
    if (ms <= missionTimesMs[0]) return missionPositions[0].clone();
    const last = missionTimesMs.length - 1;
    if (ms >= missionTimesMs[last]) return missionPositions[last].clone();

    let lo = 0;
    let hi = last;
    while (hi - lo > 1) {
      const mid = (lo + hi) >> 1;
      if (missionTimesMs[mid] <= ms) lo = mid;
      else hi = mid;
    }
    const span = missionTimesMs[hi] - missionTimesMs[lo];
    const f = span > 0 ? (ms - missionTimesMs[lo]) / span : 0;
    return missionPositions[lo].clone().lerp(missionPositions[hi], f);
  }

  function updateMissionCraft() {
    if (!missionCraft || !missionWindow) return;
    const ms = THREE.MathUtils.clamp(simDate.getTime(), missionWindow.t0, missionWindow.t1);
    const pos = missionPositionAtMs(ms);
    if (pos) missionCraft.position.copy(pos);
  }

  function focusOnMission(group: THREE.Object3D, extentUnits: number) {
    const target = new THREE.Vector3();
    group.getWorldPosition(target);
    const dist = Math.max(extentUnits * 1.6, 0.02);
    const dir = camera.position.clone().sub(controls.target);
    if (dir.lengthSq() < 1e-6) dir.set(0, 0.5, 1);
    dir.normalize().multiplyScalar(dist);
    startFocusTween(target, target.clone().add(dir).add(new THREE.Vector3(0, dist * 0.25, 0)));
  }

  function disposeObject3D(root: THREE.Object3D) {
    root.traverse((obj) => {
      if (obj instanceof THREE.Mesh || obj instanceof THREE.Line) {
        obj.geometry.dispose();
        const mats = Array.isArray(obj.material) ? obj.material : [obj.material];
        mats.forEach((m) => m.dispose());
      }
    });
  }

  function teardownMissionLayer() {
    if (missionGroup) {
      missionGroup.parent?.remove(missionGroup);
      disposeObject3D(missionGroup);
    }
    missionGroup = null;
    missionCraft = null;
    missionTimesMs = [];
    missionPositions = [];
    if (missionMoonOverride) {
      missionMoonOverride.entry.phaseDeg = missionMoonOverride.priorPhaseDeg;
      missionMoonOverride = null;
    }
  }

  function loadMission(spec: MissionSpec) {
    const wasActive = missionActive;
    teardownMissionLayer();

    if (!wasActive) {
      savedBeforeMission = {
        scaleMode,
        simDate: new Date(simDate.getTime()),
        daysPerSecond,
        cameraPos: camera.position.clone(),
        cameraTarget: controls.target.clone(),
      };
    }
    missionActive = true;

    if (scaleMode !== "true") {
      scaleMode = "true";
      applyScaleMode();
    }

    const t0 = Date.parse(spec.t0);
    const t1 = Date.parse(spec.t1);
    missionWindow = { t0, t1 };

    const group = new THREE.Group();
    const earth = bodies.find((b) => b.data.id === "earth");
    const parent: THREE.Object3D = spec.frame === "geocentric" && earth ? earth.group : scene;
    parent.add(group);
    missionGroup = group;

    if (spec.frame === "geocentric" && spec.bodyCalibration?.moon && earth) {
      const moon = earth.moons.find((m) => m.data.id === "moon");
      if (moon) {
        missionMoonOverride = { entry: moon, priorPhaseDeg: moon.phaseDeg };
        moon.phaseDeg = spec.bodyCalibration.moon.phaseDeg;
      }
    }

    const positions = spec.trajectory.map(missionPointToVector);
    missionTimesMs = spec.trajectory.map((p) => Date.parse(p.t));
    missionPositions = positions;

    let extent = 0;
    for (const v of positions) extent = Math.max(extent, v.length());
    const markerR = Math.max(extent * 0.012, 1e-4);

    const lineGeo = new THREE.BufferGeometry().setFromPoints(positions);
    const lineMat = new THREE.LineBasicMaterial({ color: 0xffd166 });
    group.add(new THREE.Line(lineGeo, lineMat));

    const craftGeo = new THREE.SphereGeometry(markerR, 16, 12);
    const craftMat = new THREE.MeshBasicMaterial({ color: 0xffffff });
    const craft = new THREE.Mesh(craftGeo, craftMat);
    group.add(craft);
    missionCraft = craft;

    const tickGeo = new THREE.SphereGeometry(markerR * 0.6, 8, 6);
    const tickMat = new THREE.MeshBasicMaterial({ color: 0xff5d73 });
    for (const m of spec.milestones) {
      const pos = missionPositionAtMs(Date.parse(m.t));
      const tick = new THREE.Mesh(tickGeo, tickMat);
      if (pos) tick.position.copy(pos);
      group.add(tick);
    }

    simDate = new Date(t0);
    updatePositions();
    updateMissionCraft();
    focusOnMission(group, extent);
  }

  function clearMission() {
    if (!missionActive) return;
    teardownMissionLayer();
    missionActive = false;
    missionWindow = null;

    const saved = savedBeforeMission;
    savedBeforeMission = null;
    if (saved) {
      if (saved.scaleMode !== scaleMode) {
        scaleMode = saved.scaleMode;
        applyScaleMode();
      }
      simDate = new Date(saved.simDate.getTime());
      daysPerSecond = saved.daysPerSecond;
      updatePositions();
      onDateTick(new Date(simDate.getTime()));
      startFocusTween(saved.cameraTarget, saved.cameraPos);
    }
  }

  function updateMoonLabelVisibility() {
    for (const body of bodies) {
      const parentSelected =
        selectedId === body.data.id ||
        body.moons.some((m) => m.data.id === selectedId);
      for (const moon of body.moons) {
        moon.labelEl.style.display = parentSelected ? "" : "none";
      }
    }
  }

  function selectBody(id: string | null) {
    selectedId = id;
    for (const body of bodies) {
      body.labelEl.classList.toggle("solar-label--active", id === body.data.id);
      for (const moon of body.moons) {
        moon.labelEl.classList.toggle("solar-label--active", id === moon.data.id);
      }
    }
    sunLabel.el.classList.toggle("solar-label--active", id === "sun");
    updateMoonLabelVisibility();
    focusOn(id);
    onSelect(id);
  }

  // Click-to-select via raycasting (drags don't select).
  const raycaster = new THREE.Raycaster();
  const pointer = new THREE.Vector2();
  let downAt: { x: number; y: number } | null = null;

  function onPointerDown(e: PointerEvent) {
    downAt = { x: e.clientX, y: e.clientY };
  }

  function onPointerUp(e: PointerEvent) {
    if (!downAt) return;
    const moved = Math.hypot(e.clientX - downAt.x, e.clientY - downAt.y);
    downAt = null;
    if (moved > 5) return;

    const rect = renderer.domElement.getBoundingClientRect();
    pointer.set(
      ((e.clientX - rect.left) / rect.width) * 2 - 1,
      -((e.clientY - rect.top) / rect.height) * 2 + 1,
    );
    raycaster.setFromCamera(pointer, camera);
    const meshes: THREE.Object3D[] = [sunMesh];
    for (const body of bodies) {
      meshes.push(body.mesh);
      for (const moon of body.moons) meshes.push(moon.mesh);
    }
    const hit = raycaster.intersectObjects(meshes, false)[0];
    selectBody(hit ? hit.object.name : null);
  }

  renderer.domElement.addEventListener("pointerdown", onPointerDown);
  renderer.domElement.addEventListener("pointerup", onPointerUp);

  // ---- resize ------------------------------------------------------------

  const resizeObserver = new ResizeObserver(() => {
    const w = container.clientWidth || 800;
    const h = container.clientHeight || 480;
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
    renderer.setSize(w, h);
    labelRenderer.setSize(w, h);
  });
  resizeObserver.observe(container);

  // ---- render loop -------------------------------------------------------

  const clock = new THREE.Clock();
  const followPos = new THREE.Vector3();
  const prevFollowPos = new THREE.Vector3();
  let hasPrevFollow = false;
  let rafId = 0;
  let tickAccumulator = 0;

  function animate() {
    if (disposed) return;
    rafId = requestAnimationFrame(animate);
    const delta = Math.min(clock.getDelta(), 0.25);

    simDate = new Date(simDate.getTime() + daysPerSecond * 86_400_000 * delta);
    if (missionWindow) {
      simDate = new Date(THREE.MathUtils.clamp(simDate.getTime(), missionWindow.t0, missionWindow.t1));
    }
    updatePositions();

    // Ride along with the selected body.
    if (selectedId && !focusTween.active && bodyWorldPosition(selectedId, followPos)) {
      if (hasPrevFollow) {
        const shift = followPos.clone().sub(prevFollowPos);
        camera.position.add(shift);
        controls.target.add(shift);
      }
      prevFollowPos.copy(followPos);
      hasPrevFollow = true;
    } else {
      hasPrevFollow = false;
    }

    if (focusTween.active) {
      focusTween.t = Math.min(focusTween.t + delta / 0.7, 1);
      const k = 1 - Math.pow(1 - focusTween.t, 3);
      // Re-anchor the destination on the moving body.
      if (selectedId && bodyWorldPosition(selectedId, followPos)) {
        const drift = followPos.clone().sub(focusTween.toTarget);
        focusTween.toTarget.add(drift);
        focusTween.toPos.add(drift);
      }
      camera.position.lerpVectors(focusTween.fromPos, focusTween.toPos, k);
      controls.target.lerpVectors(focusTween.fromTarget, focusTween.toTarget, k);
      if (focusTween.t >= 1) focusTween.active = false;
    }

    controls.update();
    renderer.render(scene, camera);
    labelRenderer.render(scene, camera);

    tickAccumulator += delta;
    if (tickAccumulator >= 0.25) {
      tickAccumulator = 0;
      onDateTick(new Date(simDate.getTime()));
    }
  }

  applyScaleMode();
  updatePositions();
  updateMoonLabelVisibility();
  animate();

  // ---- public handle -----------------------------------------------------

  return {
    setSpeed(d: number) {
      daysPerSecond = d;
    },
    setScaleMode(mode: ScaleMode) {
      // Mission mode always renders true-scale geometry (Architecture/22-…,
      // "Scale-mode lock") — a real trajectory can't terminate at the
      // visible-mode Moon's decorative display distance.
      if (missionActive) return;
      if (mode === scaleMode) return;
      scaleMode = mode;
      applyScaleMode();
      updatePositions();
      focusOn(selectedId);
    },
    setDate(date: Date) {
      const ms = missionWindow
        ? THREE.MathUtils.clamp(date.getTime(), missionWindow.t0, missionWindow.t1)
        : date.getTime();
      simDate = new Date(ms);
      updatePositions();
      onDateTick(new Date(simDate.getTime()));
    },
    select(id: string | null) {
      selectBody(id);
    },
    refreshLabels() {
      sunLabel.el.textContent = getLabel("sun");
      for (const body of bodies) {
        body.labelEl.textContent = getLabel(body.data.id);
        for (const moon of body.moons) {
          moon.labelEl.textContent = getLabel(moon.data.id);
        }
      }
    },
    mission: {
      load(spec: MissionSpec) {
        loadMission(spec);
      },
      clear() {
        clearMission();
      },
    },
    dispose() {
      disposed = true;
      teardownMissionLayer();
      cancelAnimationFrame(rafId);
      resizeObserver.disconnect();
      renderer.domElement.removeEventListener("pointerdown", onPointerDown);
      renderer.domElement.removeEventListener("pointerup", onPointerUp);
      controls.dispose();
      scene.traverse((obj) => {
        if (obj instanceof THREE.Mesh || obj instanceof THREE.Line) {
          obj.geometry.dispose();
          const mats = Array.isArray(obj.material) ? obj.material : [obj.material];
          mats.forEach((m) => m.dispose());
        }
      });
      textures.forEach((t) => t.dispose());
      renderer.dispose();
      container.removeChild(renderer.domElement);
      container.removeChild(labelRenderer.domElement);
    },
  };
}
