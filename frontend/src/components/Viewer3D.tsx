import { useEffect, useRef } from "react";
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
}

interface Props {
  items: ViewerItem[];
  selected: Set<string>;
  onSelect: (id: string | null) => void;
}

const texCache = new Map<string, THREE.Texture>();
function getTexture(url: string, loader: THREE.TextureLoader) {
  let t = texCache.get(url);
  if (!t) {
    t = loader.load(url);
    t.wrapS = t.wrapT = THREE.RepeatWrapping;
    t.wrapT = THREE.RepeatWrapping;
    t.colorSpace = THREE.SRGBColorSpace;
    t.anisotropy = 4;
    texCache.set(url, t);
  }
  return t;
}

/** Three.js part viewer: model space (x, y, z-up inches) -> three (x, z, -y). */
export default function Viewer3D({ items, selected, onSelect }: Props) {
  const hostRef = useRef<HTMLDivElement>(null);
  const stRef = useRef<{
    renderer: THREE.WebGLRenderer; scene: THREE.Scene; camera: THREE.PerspectiveCamera;
    controls: OrbitControls; group: THREE.Group; loader: THREE.TextureLoader;
  } | null>(null);
  const selectedKey = [...selected].sort().join("|");
  const onSelectRef = useRef(onSelect);
  onSelectRef.current = onSelect;

  useEffect(() => {
    const host = hostRef.current!;
    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    host.appendChild(renderer.domElement);
    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(45, 1, 0.1, 20000);
    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    scene.add(new THREE.HemisphereLight(0xcfd8e3, 0x141416, 0.9));
    const dir = new THREE.DirectionalLight(0xffffff, 1.8);
    dir.position.set(140, 200, -100);
    dir.castShadow = true;
    dir.shadow.mapSize.set(2048, 2048);
    const sc = dir.shadow.camera as THREE.OrthographicCamera;
    sc.left = -300; sc.right = 300; sc.top = 300; sc.bottom = -300; sc.far = 1200;
    scene.add(dir);
    const group = new THREE.Group();
    scene.add(group);
    stRef.current = { renderer, scene, camera, controls, group, loader: new THREE.TextureLoader() };

    const resize = () => {
      const w = host.clientWidth || 1, h = host.clientHeight || 1;
      renderer.setSize(w, h);
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
    };
    resize();
    const ro = new ResizeObserver(resize);
    ro.observe(host);

    let raf = 0;
    const tick = () => { controls.update(); renderer.render(scene, camera); raf = requestAnimationFrame(tick); };
    tick();

    let downAt: [number, number] | null = null;
    const pd = (e: PointerEvent) => { downAt = [e.clientX, e.clientY]; };
    const pu = (e: PointerEvent) => {
      if (!downAt) return;
      const moved = Math.hypot(e.clientX - downAt[0], e.clientY - downAt[1]);
      downAt = null;
      if (moved > 5) return;
      const rect = renderer.domElement.getBoundingClientRect();
      const ndc = new THREE.Vector2(
        ((e.clientX - rect.left) / rect.width) * 2 - 1,
        -((e.clientY - rect.top) / rect.height) * 2 + 1);
      const ray = new THREE.Raycaster();
      ray.setFromCamera(ndc, camera);
      const meshes = group.children.filter((c) => c.userData.partId && (c as THREE.Mesh).isMesh);
      const hits = ray.intersectObjects(meshes, false);
      onSelectRef.current(hits.length ? (hits[0].object.userData.partId as string) : null);
    };
    renderer.domElement.addEventListener("pointerdown", pd);
    renderer.domElement.addEventListener("pointerup", pu);

    return () => {
      cancelAnimationFrame(raf);
      ro.disconnect();
      renderer.domElement.removeEventListener("pointerdown", pd);
      renderer.domElement.removeEventListener("pointerup", pu);
      controls.dispose();
      renderer.dispose();
      if (renderer.domElement.parentElement === host) host.removeChild(renderer.domElement);
      stRef.current = null;
    };
  }, []);

  useEffect(() => {
    const st = stRef.current;
    if (!st) return;
    const { group, loader, camera, controls } = st;
    for (const child of [...group.children]) {
      group.remove(child);
      const m = child as THREE.Mesh;
      m.geometry?.dispose();
      const mat = m.material as THREE.Material | THREE.Material[] | undefined;
      if (Array.isArray(mat)) mat.forEach((x) => x.dispose());
      else mat?.dispose();
    }
    if (!items.length) return;

    const min = [Infinity, Infinity, Infinity];
    const max = [-Infinity, -Infinity, -Infinity];
    for (const it of items) {
      for (let i = 0; i < 3; i++) {
        min[i] = Math.min(min[i], it.bbox.min[i]);
        max[i] = Math.max(max[i], it.bbox.max[i]);
      }
    }

    const baseUV = [[0, 1], [1, 1], [0, 0], [1, 0]];
    for (const it of items) {
      const [x0, y0, z0] = it.bbox.min;
      const [x1, y1, z1] = it.bbox.max;
      const dx = Math.max(x1 - x0, 0.01), dy = Math.max(y1 - y0, 0.01), dz = Math.max(z1 - z0, 0.01);
      const geo = new THREE.BoxGeometry(dx, dz, dy);
      if (it.finish) {
        const uv = geo.attributes.uv as THREE.BufferAttribute;
        // BoxGeometry face order: +x, -x, +y(top), -y, +z, -z  -> (u,v) extents in inches
        const dims: [number, number][] = [[dy, dz], [dy, dz], [dx, dy], [dx, dy], [dx, dz], [dx, dz]];
        const sw = Math.max(it.finish.sw_w * it.finish.scale, 0.5);
        const sh = Math.max(it.finish.sw_h * it.finish.scale, 0.5);
        for (let f = 0; f < 6; f++) {
          const ru = dims[f][0] / sw, rv = dims[f][1] / sh;
          for (let k = 0; k < 4; k++) uv.setXY(f * 4 + k, baseUV[k][0] * ru, baseUV[k][1] * rv);
        }
        uv.needsUpdate = true;
      }
      const mat = it.finish
        ? new THREE.MeshStandardMaterial({
            map: getTexture(it.finish.url, loader),
            roughness: it.finish.metallic ? 0.35 : 0.72,
            metalness: it.finish.metallic ? 0.6 : 0.04,
          })
        : new THREE.MeshStandardMaterial({ color: new THREE.Color(it.color), roughness: 0.85, metalness: 0.02 });
      const mesh = new THREE.Mesh(geo, mat);
      mesh.position.set((x0 + x1) / 2, (z0 + z1) / 2, -(y0 + y1) / 2);
      mesh.castShadow = true;
      mesh.receiveShadow = true;
      mesh.userData.partId = it.id;
      group.add(mesh);

      const isSel = selected.has(it.id);
      const edge = new THREE.LineSegments(
        new THREE.EdgesGeometry(geo),
        new THREE.LineBasicMaterial({
          color: isSel ? 0xf59e0b : it.rbe ? 0x22d3ee : 0x0c0c0e,
          transparent: true,
          opacity: isSel ? 1 : it.rbe ? 0.8 : 0.35,
        }));
      edge.position.copy(mesh.position);
      group.add(edge);
    }

    const ground = new THREE.Mesh(
      new THREE.PlaneGeometry(8000, 8000),
      new THREE.ShadowMaterial({ opacity: 0.35 }));
    ground.rotation.x = -Math.PI / 2;
    ground.position.set((min[0] + max[0]) / 2, min[2], -(min[1] + max[1]) / 2);
    ground.receiveShadow = true;
    group.add(ground);

    const cx = (min[0] + max[0]) / 2, cy = (min[1] + max[1]) / 2, cz = (min[2] + max[2]) / 2;
    const radius = Math.hypot(max[0] - min[0], max[1] - min[1], max[2] - min[2]) / 2 || 50;
    camera.position.set(cx + radius * 1.5, cz + radius * 1.05, -cy - radius * 1.5);
    controls.target.set(cx, cz, -cy);
    controls.update();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [items, selectedKey]);

  return <div ref={hostRef} className="h-full w-full" />;
}
