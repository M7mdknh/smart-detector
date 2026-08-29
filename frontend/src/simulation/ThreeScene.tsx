import { useEffect, useRef } from "react";
import * as THREE from "three";
import type { SimulationState } from "../api/types";

const GAS_ZONE = { x1: 3, y1: 3, x2: 8, y2: 8 };
const OVERHEAD_ZONE = { x1: -8, y1: -8, x2: -3, y2: -3 };
const FLOOR_HALF = 12;

export function ThreeScene({
  state,
  onFloorClick,
}: {
  state: SimulationState | null | undefined;
  onFloorClick: (x: number, y: number) => void;
}) {
  const mountRef = useRef<HTMLDivElement>(null);
  const workerRef = useRef<THREE.Mesh | null>(null);
  const gasZoneMatRef = useRef<THREE.MeshStandardMaterial | null>(null);
  const stateRef = useRef(state);
  stateRef.current = state;

  useEffect(() => {
    const mount = mountRef.current;
    if (!mount) return;

    if (!("WebGLRenderingContext" in window)) {
      mount.textContent = "WebGL is unavailable in this browser. Use the control panel below to operate the simulation.";
      return;
    }

    const width = mount.clientWidth;
    const height = 420;

    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0x14161c);

    const camera = new THREE.PerspectiveCamera(45, width / height, 0.1, 200);
    camera.position.set(18, 16, 18);
    camera.lookAt(0, 0, 0);

    const renderer = new THREE.WebGLRenderer({ antialias: true });
    renderer.setSize(width, height);
    mount.innerHTML = "";
    mount.appendChild(renderer.domElement);

    scene.add(new THREE.AmbientLight(0xffffff, 0.7));
    const dirLight = new THREE.DirectionalLight(0xffffff, 0.6);
    dirLight.position.set(10, 20, 10);
    scene.add(dirLight);

    // Floor
    const floor = new THREE.Mesh(
      new THREE.PlaneGeometry(FLOOR_HALF * 2, FLOOR_HALF * 2),
      new THREE.MeshStandardMaterial({ color: 0x2a2f3a }),
    );
    floor.rotation.x = -Math.PI / 2;
    floor.name = "floor";
    scene.add(floor);

    const grid = new THREE.GridHelper(FLOOR_HALF * 2, 20, 0x444a58, 0x333844);
    scene.add(grid);

    // Gas exposure zone (translucent red plane)
    const gasZoneMat = new THREE.MeshStandardMaterial({ color: 0xc62828, transparent: true, opacity: 0.25 });
    gasZoneMatRef.current = gasZoneMat;
    const gasZone = new THREE.Mesh(
      new THREE.PlaneGeometry(GAS_ZONE.x2 - GAS_ZONE.x1, GAS_ZONE.y2 - GAS_ZONE.y1),
      gasZoneMat,
    );
    gasZone.rotation.x = -Math.PI / 2;
    gasZone.position.set((GAS_ZONE.x1 + GAS_ZONE.x2) / 2, 0.02, (GAS_ZONE.y1 + GAS_ZONE.y2) / 2);
    scene.add(gasZone);

    // Overhead-work zone (translucent amber plane)
    const overheadZone = new THREE.Mesh(
      new THREE.PlaneGeometry(OVERHEAD_ZONE.x2 - OVERHEAD_ZONE.x1, OVERHEAD_ZONE.y2 - OVERHEAD_ZONE.y1),
      new THREE.MeshStandardMaterial({ color: 0xc98a1d, transparent: true, opacity: 0.2 }),
    );
    overheadZone.rotation.x = -Math.PI / 2;
    overheadZone.position.set((OVERHEAD_ZONE.x1 + OVERHEAD_ZONE.x2) / 2, 0.02, (OVERHEAD_ZONE.y1 + OVERHEAD_ZONE.y2) / 2);
    scene.add(overheadZone);

    // Machines (simple boxes)
    for (const [mx, mz] of [[-3, 3], [3, -3]]) {
      const machine = new THREE.Mesh(new THREE.BoxGeometry(1.2, 1.2, 1.2), new THREE.MeshStandardMaterial({ color: 0x556070 }));
      machine.position.set(mx, 0.6, mz);
      scene.add(machine);
    }

    // Ventilation marker
    const vent = new THREE.Mesh(new THREE.CylinderGeometry(0.4, 0.4, 1.5, 12), new THREE.MeshStandardMaterial({ color: 0x6fb3ff }));
    vent.position.set(-9, 0.75, 9);
    scene.add(vent);

    // Camera cone (represents the fixed CV camera, not the viewport camera)
    const camCone = new THREE.Mesh(new THREE.ConeGeometry(0.4, 1, 8), new THREE.MeshStandardMaterial({ color: 0xe5e7eb }));
    camCone.position.set(0, 3, -9);
    camCone.rotation.x = Math.PI;
    scene.add(camCone);

    // Worker capsule
    const worker = new THREE.Mesh(
      new THREE.CapsuleGeometry(0.4, 1.2, 4, 8),
      new THREE.MeshStandardMaterial({ color: 0x3f9142 }),
    );
    worker.position.set(0, 1, 0);
    scene.add(worker);
    workerRef.current = worker;

    const label = document.createElement("div");
    label.className = "gt-label";
    label.textContent = "Simulation ground truth";
    mount.appendChild(label);

    const raycaster = new THREE.Raycaster();
    const pointer = new THREE.Vector2();

    function handleClick(ev: MouseEvent) {
      const rect = renderer.domElement.getBoundingClientRect();
      pointer.x = ((ev.clientX - rect.left) / rect.width) * 2 - 1;
      pointer.y = -((ev.clientY - rect.top) / rect.height) * 2 + 1;
      raycaster.setFromCamera(pointer, camera);
      const hit = raycaster.intersectObject(floor)[0];
      if (hit) {
        onFloorClick(hit.point.x, hit.point.z);
      }
    }
    renderer.domElement.addEventListener("click", handleClick);

    let raf = 0;
    function animate() {
      const s = stateRef.current;
      if (s && workerRef.current) {
        workerRef.current.position.x = s.worker_x;
        workerRef.current.position.z = s.worker_y;
        const mat = workerRef.current.material as THREE.MeshStandardMaterial;
        mat.color.set(s.worker_helmet ? 0x3f9142 : 0xc62828);
      }
      if (gasZoneMatRef.current && s) {
        const intensity = Math.min(1, Math.max(0.15, s.source_ppm_m3_per_h / 6_000_000));
        gasZoneMatRef.current.opacity = 0.15 + intensity * 0.5;
      }
      renderer.render(scene, camera);
      raf = requestAnimationFrame(animate);
    }
    animate();

    return () => {
      cancelAnimationFrame(raf);
      renderer.domElement.removeEventListener("click", handleClick);
      renderer.dispose();
      mount.innerHTML = "";
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return <div ref={mountRef} className="three-mount" />;
}
