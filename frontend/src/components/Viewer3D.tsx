import { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import type { BBox } from "../types";

export interface ViewerItem {
  id: string;
  name: string;
  bbox: BBox;
  finish: { url: string; sw_w: number; sw_h: number; scale: number; metallic: boolean } | null;
  color: string;
  rbe: boolean;
  conflict?: boolean;
}
interface PreviewPart { id: string; positions: number[]; triangles: number[]; lines: number[] }
interface PreviewGeometry { version: number; units: string; parts: PreviewPart[] }
interface Props {
  items: ViewerItem[];
  selected: Set<string>;
  onSelect: (id: string | null) => void;
  geometryUrl?: string;
  partial?: boolean;
  simulatedGeometry?: boolean;
}

const texCache = new Map<string, THREE.Texture>();
function getTexture(url: string, loader: THREE.TextureLoader) {
  let texture = texCache.get(url);
  if (!texture) {
    texture = loader.load(url);
    texture.wrapS = texture.wrapT = THREE.RepeatWrapping;
    texture.colorSpace = THREE.SRGBColorSpace;
    texture.anisotropy = 4;
    texCache.set(url, texture);
  }
  return texture;
}

function positionsInThree(points: number[], origin: number[]): number[] {
  const out: number[] = [];
  for (let i = 0; i < points.length; i += 3) out.push(points[i] - origin[0], points[i + 2] - origin[2], -(points[i + 1] - origin[1]));
  return out;
}

/** Project each triangle using its dominant face. This is an approximate UI preview,
 * not a promise that the final V-Ray material/mapping will look identical. */
function meshGeometry(part: PreviewPart, finish: ViewerItem["finish"], origin: number[]): THREE.BufferGeometry {
  const indexed = new THREE.BufferGeometry();
  indexed.setAttribute("position", new THREE.Float32BufferAttribute(positionsInThree(part.positions, origin), 3));
  indexed.setIndex(part.triangles);
  indexed.computeVertexNormals();
  if (!finish) return indexed;
  const geo = indexed.toNonIndexed();
  indexed.dispose();
  const uv: number[] = [];
  const sw = Math.max(finish.sw_w * finish.scale, 0.00001);
  const sh = Math.max(finish.sw_h * finish.scale, 0.00001);
  for (let i = 0; i < part.triangles.length; i += 3) {
    const vertices = part.triangles.slice(i, i + 3).map((n) =>
      new THREE.Vector3(part.positions[n * 3], part.positions[n * 3 + 1], part.positions[n * 3 + 2]));
    const normal = new THREE.Vector3().crossVectors(
      new THREE.Vector3().subVectors(vertices[1], vertices[0]),
      new THREE.Vector3().subVectors(vertices[2], vertices[0]));
    const nx = Math.abs(normal.x), ny = Math.abs(normal.y), nz = Math.abs(normal.z);
    for (const p of vertices) {
      if (nz >= nx && nz >= ny) uv.push(p.x / sw, p.y / sh);
      else if (nx >= ny) uv.push(p.y / sw, p.z / sh);
      else uv.push(p.x / sw, p.z / sh);
    }
  }
  geo.setAttribute("uv", new THREE.Float32BufferAttribute(uv, 2));
  return geo;
}

/** Rhino model space (x, y, z-up inches) -> Three.js (x, z, -y). */
export default function Viewer3D({ items, selected, onSelect, geometryUrl, partial, simulatedGeometry }: Props) {
  const hostRef = useRef<HTMLDivElement>(null);
  const state = useRef<{
    renderer: THREE.WebGLRenderer; scene: THREE.Scene; camera: THREE.PerspectiveCamera;
    controls: OrbitControls; group: THREE.Group; loader: THREE.TextureLoader; framed: string;
  } | null>(null);
  const [geometry, setGeometry] = useState<PreviewGeometry | null>(null);
  const [status, setStatus] = useState<"box" | "loading" | "mesh" | "error">("box");
  const selectedKey = [...selected].sort().join("|");
  const onSelectRef = useRef(onSelect);
  onSelectRef.current = onSelect;

  useEffect(() => {
    if (!geometryUrl) { setGeometry(null); setStatus("box"); return; }
    const controller = new AbortController();
    setGeometry(null); setStatus("loading");
    fetch(geometryUrl, { signal: controller.signal }).then(async (response) => {
      if (!response.ok) throw new Error("geometry unavailable");
      const data: PreviewGeometry = await response.json();
      if (data.version !== 1 || data.units !== "inches" || !Array.isArray(data.parts)) throw new Error("bad geometry");
      setGeometry(data); setStatus("mesh");
    }).catch((err) => { if (err.name !== "AbortError") setStatus("error"); });
    return () => controller.abort();
  }, [geometryUrl]);

  useEffect(() => {
    const host = hostRef.current!;
    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    host.appendChild(renderer.domElement);
    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(45, 1, 0.01, 1000000);
    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    scene.add(new THREE.HemisphereLight(0xcfd8e3, 0x141416, 1.2));
    const light = new THREE.DirectionalLight(0xffffff, 1.8);
    light.position.set(140, 200, -100); scene.add(light);
    const group = new THREE.Group(); scene.add(group);
    state.current = { renderer, scene, camera, controls, group, loader: new THREE.TextureLoader(), framed: "" };
    const resize = () => {
      const w = host.clientWidth || 1, h = host.clientHeight || 1;
      renderer.setSize(w, h); camera.aspect = w / h; camera.updateProjectionMatrix();
    };
    resize();
    const ro = new ResizeObserver(resize); ro.observe(host);
    let raf = 0;
    const tick = () => { controls.update(); renderer.render(scene, camera); raf = requestAnimationFrame(tick); };
    tick();
    let downAt: [number, number] | null = null;
    const pd = (e: PointerEvent) => { downAt = [e.clientX, e.clientY]; };
    const pu = (e: PointerEvent) => {
      if (!downAt) return;
      const moved = Math.hypot(e.clientX - downAt[0], e.clientY - downAt[1]); downAt = null;
      if (moved > 5) return;
      const rect = renderer.domElement.getBoundingClientRect();
      const ndc = new THREE.Vector2(((e.clientX - rect.left) / rect.width) * 2 - 1,
        -((e.clientY - rect.top) / rect.height) * 2 + 1);
      const ray = new THREE.Raycaster(); ray.setFromCamera(ndc, camera);
      ray.params.Line = { threshold: Math.max(0.02, camera.position.distanceTo(controls.target) * 0.003) };
      const hits = ray.intersectObjects(group.children.filter((c) => c.userData.partId), false);
      onSelectRef.current(hits.length ? (hits[0].object.userData.partId as string) : null);
    };
    renderer.domElement.addEventListener("pointerdown", pd);
    renderer.domElement.addEventListener("pointerup", pu);
    return () => {
      cancelAnimationFrame(raf); ro.disconnect();
      renderer.domElement.removeEventListener("pointerdown", pd);
      renderer.domElement.removeEventListener("pointerup", pu);
      controls.dispose(); renderer.dispose();
      if (renderer.domElement.parentElement === host) host.removeChild(renderer.domElement);
      state.current = null;
    };
  }, []);

  useEffect(() => {
    const st = state.current;
    if (!st) return;
    const { group, loader, camera, controls } = st;
    for (const child of [...group.children]) {
      group.remove(child);
      const obj = child as THREE.Mesh;
      obj.geometry?.dispose();
      const material = obj.material as THREE.Material | THREE.Material[] | undefined;
      if (Array.isArray(material)) material.forEach((m) => m.dispose()); else material?.dispose();
    }
    if (!items.length) return;
    const min = [Infinity, Infinity, Infinity], max = [-Infinity, -Infinity, -Infinity];
    for (const item of items) for (let i = 0; i < 3; i++) {
      min[i] = Math.min(min[i], item.bbox.min[i]); max[i] = Math.max(max[i], item.bbox.max[i]);
    }
    // Recenter before converting to float32 so large CAD coordinates retain detail.
    const origin = min.map((v, i) => (v + max[i]) / 2);
    const geometryById = new Map((geometry?.parts || []).map((part) => [part.id, part]));
    const showBoxes = !geometry;
    for (const item of items) {
      const part = geometryById.get(item.id);
      const isSelected = selected.has(item.id);
      if (part && part.positions.length && part.triangles.length) {
        const geo = meshGeometry(part, item.finish, origin);
        const mat = new THREE.MeshStandardMaterial({
          color: item.finish ? 0xffffff : new THREE.Color(item.color),
          map: item.finish ? getTexture(item.finish.url, loader) : null,
          roughness: item.finish?.metallic ? 0.35 : 0.8,
          metalness: item.finish?.metallic ? 0.6 : 0.02,
          emissive: isSelected ? 0x704600 : item.rbe ? 0x052027 : 0x000000,
          side: THREE.DoubleSide,
        });
        const mesh = new THREE.Mesh(geo, mat);
        mesh.userData.partId = item.id; group.add(mesh);
      }
      if (part && part.positions.length && part.lines.length) {
        const geo = new THREE.BufferGeometry();
        geo.setAttribute("position", new THREE.Float32BufferAttribute(positionsInThree(part.positions, origin), 3));
        geo.setIndex(part.lines);
        const lines = new THREE.LineSegments(geo, new THREE.LineBasicMaterial({ color: isSelected ? 0xf59e0b : item.color }));
        lines.userData.partId = item.id; group.add(lines);
      }
      if (showBoxes) {
        const [x0, y0, z0] = item.bbox.min, [x1, y1, z1] = item.bbox.max;
        const geo = new THREE.BoxGeometry(Math.max(x1 - x0, 0.01), Math.max(z1 - z0, 0.01), Math.max(y1 - y0, 0.01));
        if (item.finish) {
          const uv = geo.attributes.uv as THREE.BufferAttribute;
          const base = [[0, 1], [1, 1], [0, 0], [1, 0]];
          const dx = x1 - x0, dy = y1 - y0, dz = z1 - z0;
          const dims = [[dy, dz], [dy, dz], [dx, dy], [dx, dy], [dx, dz], [dx, dz]];
          const sw = Math.max(item.finish.sw_w * item.finish.scale, 0.00001);
          const sh = Math.max(item.finish.sw_h * item.finish.scale, 0.00001);
          for (let f = 0; f < 6; f++) for (let k = 0; k < 4; k++)
            uv.setXY(f * 4 + k, base[k][0] * dims[f][0] / sw, base[k][1] * dims[f][1] / sh);
          uv.needsUpdate = true;
        }
        const mat = new THREE.MeshStandardMaterial({ color: item.finish ? 0xffffff : new THREE.Color(item.color),
          map: item.finish ? getTexture(item.finish.url, loader) : null,
          emissive: isSelected ? 0x704600 : 0x000000, roughness: 0.85 });
        const box = new THREE.Mesh(geo, mat);
        box.position.set((x0 + x1) / 2 - origin[0], (z0 + z1) / 2 - origin[2], -((y0 + y1) / 2 - origin[1]));
        box.userData.partId = item.id; group.add(box);
        const edges = new THREE.LineSegments(new THREE.EdgesGeometry(geo),
          new THREE.LineBasicMaterial({ color: isSelected ? 0xf59e0b : item.rbe ? 0x22d3ee : 0x111111 }));
        edges.position.copy(box.position); group.add(edges);
      }
    }
    const frameKey = `${geometryUrl || "boxes"}:${min.join(",")}:${max.join(",")}:${items.map((i) => i.id).join("|")}`;
    if (st.framed !== frameKey) {
      const radius = Math.hypot(max[0] - min[0], max[1] - min[1], max[2] - min[2]) / 2 || 50;
      camera.position.set(radius * 1.5, radius * 1.05, -radius * 1.5);
      camera.near = Math.max(radius / 10000, 0.001); camera.far = Math.max(radius * 100, 10000);
      camera.updateProjectionMatrix(); controls.target.set(0, 0, 0); controls.update();
      st.framed = frameKey;
    }
  }, [items, geometry, geometryUrl, selectedKey]);

  const label = status === "loading" ? "Loading Rhino geometry… (boxes shown temporarily)"
    : status === "error" ? "Geometry could not be loaded — bounding-box fallback"
    : status === "mesh" ? (simulatedGeometry ? "Synthetic test geometry — not Rhino" : partial ? "Partial Rhino tessellation — some objects omitted" : "Rhino tessellated geometry · finish preview is approximate")
    : "Bounding-box fallback — not actual CAD geometry";
  return <div className="h-full w-full"><div ref={hostRef} className="h-full w-full" />
    <div className="pointer-events-none absolute bottom-4 left-4 rounded-lg border border-zinc-700 bg-zinc-950/85 px-3 py-2 text-[11px] text-zinc-300">{label}</div>
  </div>;
}
