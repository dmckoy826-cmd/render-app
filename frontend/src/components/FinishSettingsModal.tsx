import { useState } from "react";
import type { Finish } from "../types";

export interface FinishTransformSettings {
  scale_multiplier: number;
  rotation_deg: number;
  offset_u_in: number;
  offset_v_in: number;
}

interface Props {
  targetLabel: string;
  finish: Finish;
  initial: FinishTransformSettings;
  onApply: (next: FinishTransformSettings) => void;
  onClose: () => void;
}

const SCALE_PRESETS = [0.25, 0.5, 0.75, 1, 1.5, 2, 4];
const ROTATION_PRESETS = [0, 15, 30, 45, 60, 75, 90];

export function formatTransformSummary(s: {
  scale_multiplier?: number;
  rotation_deg?: number;
  offset_u_in?: number;
  offset_v_in?: number;
}): string {
  const scale = Number((s.scale_multiplier ?? 1).toFixed(2));
  const rot = Number((s.rotation_deg ?? 0).toFixed(0));
  const u = Number((s.offset_u_in ?? 0).toFixed(2));
  const v = Number((s.offset_v_in ?? 0).toFixed(2));
  const parts = [`${scale}×`];
  parts.push(`${rot}°`);
  if (Math.abs(u) > 0.001 || Math.abs(v) > 0.001) {
    parts.push(`Offset ${u >= 0 ? `+${u}` : u}", ${v >= 0 ? `+${v}` : v}"`);
  }
  return parts.join(" · ");
}

export default function FinishSettingsModal({
  targetLabel,
  finish,
  initial,
  onApply,
  onClose,
}: Props) {
  const [scale, setScale] = useState<number>(
    initial.scale_multiplier > 0 ? initial.scale_multiplier : 1
  );
  const [rotation, setRotation] = useState<number>(
    Math.min(90, Math.max(0, Number(initial.rotation_deg ?? 0)))
  );
  const [offsetU, setOffsetU] = useState<number>(Number(initial.offset_u_in ?? 0));
  const [offsetV, setOffsetV] = useState<number>(Number(initial.offset_v_in ?? 0));

  const baseW = Math.max(0.1, finish.swatch_width_in || 12);
  const baseH = Math.max(0.1, finish.swatch_height_in || 12);
  const effectiveW = Number((baseW * scale).toFixed(2));
  const effectiveH = Number((baseH * scale).toFixed(2));

  const clampScale = (val: number) => {
    if (!Number.isFinite(val) || val <= 0) return 1;
    return Math.min(100, Math.max(0.05, Number(val.toFixed(4))));
  };

  const clampRotation = (val: number) => {
    if (!Number.isFinite(val)) return 0;
    return Math.min(90, Math.max(0, Number(val.toFixed(1))));
  };

  const clampOffset = (val: number) => {
    if (!Number.isFinite(val)) return 0;
    return Math.min(1000, Math.max(-1000, Number(val.toFixed(2))));
  };

  const resetDefaults = () => {
    setScale(1);
    setRotation(0);
    setOffsetU(0);
    setOffsetV(0);
  };

  // Visual preview math: show ~2x2 tiles at 1x scale inside the preview box
  const previewTilePx = Math.min(180, Math.max(28, 72 * Math.sqrt(scale)));
  const previewShiftX = (offsetU / Math.max(0.1, effectiveW)) * previewTilePx;
  const previewShiftY = -(offsetV / Math.max(0.1, effectiveH)) * previewTilePx;

  return (
    <div
      className="fixed inset-0 z-[60] bg-black/75 backdrop-blur-sm flex items-center justify-center p-4"
      onClick={onClose}
    >
      <div
        className="w-full max-w-2xl bg-zinc-900 border border-zinc-800 rounded-2xl shadow-2xl overflow-hidden flex flex-col max-h-[90vh]"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="px-5 py-4 border-b border-zinc-800 flex items-center justify-between">
          <div className="flex items-center gap-3 min-w-0">
            <img
              src={finish.thumb_url}
              alt={finish.name}
              className="w-10 h-10 rounded-lg object-cover border border-zinc-700 shrink-0"
            />
            <div className="min-w-0">
              <div className="text-[11px] uppercase tracking-wider text-amber-400 font-medium truncate">
                Finish Scale · Rotation · Seam Offset
              </div>
              <h3 className="font-semibold text-base text-zinc-100 truncate">
                {finish.name}{" "}
                <span className="text-zinc-500 font-normal">on {targetLabel}</span>
              </h3>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800"
          >
            ✕
          </button>
        </div>

        <div className="p-5 space-y-5 overflow-y-auto">
          {/* Top row: Live visual preview + current summary */}
          <div className="grid grid-cols-[180px_1fr] gap-4 bg-zinc-950/70 border border-zinc-800/80 rounded-xl p-3.5 items-center">
            <div className="relative w-[180px] h-[132px] rounded-lg overflow-hidden border border-zinc-700 bg-zinc-900">
              <div
                className="absolute inset-[-100%] pointer-events-none"
                style={{
                  backgroundImage: `url(${finish.image_url || finish.thumb_url})`,
                  backgroundRepeat: "repeat",
                  backgroundSize: `${previewTilePx}px ${
                    previewTilePx * (baseH / baseW)
                  }px`,
                  backgroundPosition: `calc(50% + ${previewShiftX}px) calc(50% + ${previewShiftY}px)`,
                  transform: `rotate(${-rotation}deg)`,
                  transformOrigin: "center center",
                }}
              />
              {/* Subtle seam alignment crosshair */}
              <div
                className="absolute inset-[-100%] pointer-events-none opacity-45"
                style={{
                  backgroundImage:
                    "linear-gradient(to right, rgba(245,158,11,0.55) 1px, transparent 1px), linear-gradient(to bottom, rgba(245,158,11,0.55) 1px, transparent 1px)",
                  backgroundSize: `${previewTilePx}px ${
                    previewTilePx * (baseH / baseW)
                  }px`,
                  backgroundPosition: `calc(50% + ${previewShiftX}px) calc(50% + ${previewShiftY}px)`,
                  transform: `rotate(${-rotation}deg)`,
                  transformOrigin: "center center",
                }}
              />
              <div className="absolute bottom-1.5 left-1.5 right-1.5 px-2 py-0.5 rounded bg-black/75 text-[10px] font-mono text-amber-300 flex items-center justify-between">
                <span>Tile + Seam Grid</span>
                <span>{rotation}°</span>
              </div>
            </div>

            <div className="space-y-2 text-xs">
              <div className="flex items-center justify-between">
                <span className="text-zinc-400">Base Swatch Size:</span>
                <span className="font-mono text-zinc-200">
                  {baseW}" × {baseH}"
                </span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-zinc-400">Effective Tile Size in Rhino:</span>
                <span className="font-mono text-amber-300 font-semibold">
                  {effectiveW}" × {effectiveH}" ({Number(scale.toFixed(2))}×)
                </span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-zinc-400">Grain / Texture Rotation:</span>
                <span className="font-mono text-zinc-200">{rotation}°</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-zinc-400">Seam Origin Offset (U, V):</span>
                <span className="font-mono text-zinc-200">
                  {offsetU >= 0 ? `+${offsetU}` : offsetU}",{" "}
                  {offsetV >= 0 ? `+${offsetV}` : offsetV}"
                </span>
              </div>
              <div className="pt-1 text-[11px] text-zinc-500">
                Amber dashed lines preview where tile edges/seams fall. Adjust{" "}
                <span className="text-zinc-300">Seam Offset</span> below to push seams off
                part boundaries.
              </div>
            </div>
          </div>

          {/* 1. Scale Section */}
          <div className="bg-zinc-950/50 border border-zinc-800 rounded-xl p-4 space-y-3">
            <div className="flex items-center justify-between">
              <label className="text-xs font-medium text-zinc-200 flex items-center gap-1.5">
                <span className="text-amber-400">⤢</span>
                1. Texture Scale & Physical Tile Size
              </label>
              <div className="flex items-center gap-1">
                {SCALE_PRESETS.map((p) => (
                  <button
                    key={p}
                    type="button"
                    onClick={() => setScale(p)}
                    className={`px-2 py-0.5 rounded text-[11px] font-mono border transition ${
                      Math.abs(scale - p) < 0.001
                        ? "bg-amber-400/20 border-amber-400 text-amber-200"
                        : "bg-zinc-900 border-zinc-800 text-zinc-400 hover:text-zinc-200"
                    }`}
                  >
                    {p}×
                  </button>
                ))}
              </div>
            </div>

            <div className="grid grid-cols-3 gap-3">
              <div>
                <div className="text-[11px] text-zinc-400 mb-1">Scale Multiplier (×)</div>
                <input
                  type="number"
                  min={0.05}
                  max={100}
                  step={0.05}
                  value={Number(scale.toFixed(3))}
                  onChange={(e) => setScale(clampScale(Number(e.target.value)))}
                  className="w-full px-2.5 py-1.5 rounded-lg bg-zinc-900 border border-zinc-800 text-xs font-mono text-zinc-100"
                />
              </div>
              <div>
                <div className="text-[11px] text-zinc-400 mb-1">Target Tile Width (in)</div>
                <input
                  type="number"
                  min={0.25}
                  max={2000}
                  step={0.5}
                  value={effectiveW}
                  onChange={(e) => {
                    const w = Number(e.target.value);
                    if (w > 0) setScale(clampScale(w / baseW));
                  }}
                  className="w-full px-2.5 py-1.5 rounded-lg bg-zinc-900 border border-zinc-800 text-xs font-mono text-zinc-100"
                />
              </div>
              <div>
                <div className="text-[11px] text-zinc-400 mb-1">Target Tile Height (in)</div>
                <input
                  type="number"
                  min={0.25}
                  max={2000}
                  step={0.5}
                  value={effectiveH}
                  onChange={(e) => {
                    const h = Number(e.target.value);
                    if (h > 0) setScale(clampScale(h / baseH));
                  }}
                  className="w-full px-2.5 py-1.5 rounded-lg bg-zinc-900 border border-zinc-800 text-xs font-mono text-zinc-100"
                />
              </div>
            </div>
          </div>

          {/* 2. Rotation (0 - 90 deg) */}
          <div className="bg-zinc-950/50 border border-zinc-800 rounded-xl p-4 space-y-3">
            <div className="flex items-center justify-between">
              <label className="text-xs font-medium text-zinc-200 flex items-center gap-1.5">
                <span className="text-amber-400">↻</span>
                2. Grain / Pattern Rotation (0° – 90°)
              </label>
              <div className="flex items-center gap-1">
                {ROTATION_PRESETS.map((deg) => (
                  <button
                    key={deg}
                    type="button"
                    onClick={() => setRotation(deg)}
                    className={`px-2 py-0.5 rounded text-[11px] font-mono border transition ${
                      Math.abs(rotation - deg) < 0.1
                        ? "bg-amber-400/20 border-amber-400 text-amber-200"
                        : "bg-zinc-900 border-zinc-800 text-zinc-400 hover:text-zinc-200"
                    }`}
                  >
                    {deg}°
                  </button>
                ))}
              </div>
            </div>

            <div className="flex items-center gap-3">
              <input
                type="range"
                min={0}
                max={90}
                step={1}
                value={rotation}
                onChange={(e) => setRotation(clampRotation(Number(e.target.value)))}
                className="flex-1 accent-amber-400"
              />
              <div className="flex items-center gap-1.5 shrink-0">
                <input
                  type="number"
                  min={0}
                  max={90}
                  step={1}
                  value={rotation}
                  onChange={(e) => setRotation(clampRotation(Number(e.target.value)))}
                  className="w-20 px-2.5 py-1.5 rounded-lg bg-zinc-900 border border-zinc-800 text-xs font-mono text-zinc-100 text-right"
                />
                <span className="text-xs text-zinc-400 font-mono">deg</span>
              </div>
            </div>
          </div>

          {/* 3. Seam Offset (U, V in inches) */}
          <div className="bg-zinc-950/50 border border-zinc-800 rounded-xl p-4 space-y-3">
            <div className="flex items-center justify-between">
              <div>
                <label className="text-xs font-medium text-zinc-200 flex items-center gap-1.5">
                  <span className="text-amber-400">✥</span>
                  3. Seam Offset (Prevent Seams on Parts)
                </label>
                <p className="text-[11px] text-zinc-500 mt-0.5">
                  Shift the texture mapping origin in inches along U (horizontal) or V (vertical)
                  so tile edges don't show up across a part.
                </p>
              </div>
              <button
                type="button"
                onClick={() => {
                  setOffsetU(Number((effectiveW * 0.5).toFixed(2)));
                  setOffsetV(Number((effectiveH * 0.5).toFixed(2)));
                }}
                className="px-2.5 py-1 rounded-lg bg-zinc-900 border border-zinc-800 hover:border-amber-400/50 text-[11px] text-amber-300 shrink-0"
              >
                Shift Half-Tile (+½ W, +½ H)
              </button>
            </div>

            <div className="grid grid-cols-2 gap-4 pt-1">
              <div className="space-y-1.5">
                <div className="flex items-center justify-between text-[11px]">
                  <span className="text-zinc-300">Horizontal Offset (U, inches)</span>
                  <div className="flex items-center gap-1">
                    <button
                      type="button"
                      onClick={() => setOffsetU(0)}
                      className="px-1.5 py-0.5 rounded bg-zinc-900 border border-zinc-800 text-[10px] text-zinc-400 hover:text-zinc-200"
                    >
                      0"
                    </button>
                    <button
                      type="button"
                      onClick={() => setOffsetU(Number((effectiveW * 0.25).toFixed(2)))}
                      className="px-1.5 py-0.5 rounded bg-zinc-900 border border-zinc-800 text-[10px] text-zinc-400 hover:text-zinc-200"
                    >
                      +¼ W
                    </button>
                    <button
                      type="button"
                      onClick={() => setOffsetU(Number((effectiveW * 0.5).toFixed(2)))}
                      className="px-1.5 py-0.5 rounded bg-zinc-900 border border-zinc-800 text-[10px] text-zinc-400 hover:text-zinc-200"
                    >
                      +½ W
                    </button>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <input
                    type="range"
                    min={-effectiveW}
                    max={effectiveW}
                    step={0.25}
                    value={Math.max(-effectiveW, Math.min(effectiveW, offsetU))}
                    onChange={(e) => setOffsetU(clampOffset(Number(e.target.value)))}
                    className="flex-1 accent-amber-400"
                  />
                  <input
                    type="number"
                    step={0.25}
                    value={offsetU}
                    onChange={(e) => setOffsetU(clampOffset(Number(e.target.value)))}
                    className="w-20 px-2 py-1 rounded-lg bg-zinc-900 border border-zinc-800 text-xs font-mono text-zinc-100 text-right"
                  />
                  <span className="text-xs text-zinc-500 font-mono">in</span>
                </div>
              </div>

              <div className="space-y-1.5">
                <div className="flex items-center justify-between text-[11px]">
                  <span className="text-zinc-300">Vertical Offset (V, inches)</span>
                  <div className="flex items-center gap-1">
                    <button
                      type="button"
                      onClick={() => setOffsetV(0)}
                      className="px-1.5 py-0.5 rounded bg-zinc-900 border border-zinc-800 text-[10px] text-zinc-400 hover:text-zinc-200"
                    >
                      0"
                    </button>
                    <button
                      type="button"
                      onClick={() => setOffsetV(Number((effectiveH * 0.25).toFixed(2)))}
                      className="px-1.5 py-0.5 rounded bg-zinc-900 border border-zinc-800 text-[10px] text-zinc-400 hover:text-zinc-200"
                    >
                      +¼ H
                    </button>
                    <button
                      type="button"
                      onClick={() => setOffsetV(Number((effectiveH * 0.5).toFixed(2)))}
                      className="px-1.5 py-0.5 rounded bg-zinc-900 border border-zinc-800 text-[10px] text-zinc-400 hover:text-zinc-200"
                    >
                      +½ H
                    </button>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <input
                    type="range"
                    min={-effectiveH}
                    max={effectiveH}
                    step={0.25}
                    value={Math.max(-effectiveH, Math.min(effectiveH, offsetV))}
                    onChange={(e) => setOffsetV(clampOffset(Number(e.target.value)))}
                    className="flex-1 accent-amber-400"
                  />
                  <input
                    type="number"
                    step={0.25}
                    value={offsetV}
                    onChange={(e) => setOffsetV(clampOffset(Number(e.target.value)))}
                    className="w-20 px-2 py-1 rounded-lg bg-zinc-900 border border-zinc-800 text-xs font-mono text-zinc-100 text-right"
                  />
                  <span className="text-xs text-zinc-500 font-mono">in</span>
                </div>
              </div>
            </div>
          </div>
        </div>

        <div className="px-5 py-3.5 border-t border-zinc-800 bg-zinc-950/60 flex items-center justify-between">
          <button
            type="button"
            onClick={resetDefaults}
            className="px-3 py-1.5 rounded-lg text-xs text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800 inline-flex items-center gap-1.5"
          >
            <span>↺</span>
            Reset (1× · 0° · 0", 0")
          </button>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 rounded-lg text-sm text-zinc-400 hover:text-zinc-200"
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={() =>
                onApply({
                  scale_multiplier: clampScale(scale),
                  rotation_deg: clampRotation(rotation),
                  offset_u_in: clampOffset(offsetU),
                  offset_v_in: clampOffset(offsetV),
                })
              }
              className="px-5 py-2 rounded-lg bg-amber-400 hover:bg-amber-300 text-zinc-950 font-semibold text-sm"
            >
              Apply Finish Settings
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
