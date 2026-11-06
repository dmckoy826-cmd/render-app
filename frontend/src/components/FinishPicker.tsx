import { useEffect, useState } from "react";
import Modal from "./Modal";
import { api, toast } from "../api";
import { usePoll } from "../hooks";
import { CATEGORY_COLOR, CATEGORY_LABEL, type Category, type Finish } from "../types";

const CATS: ("all" | Category)[] = ["all", "laminate", "pet", "product_finish", "other"];
const SCALES_STORAGE_KEY = "ff_saved_scales_v1";

export interface SavedScaleItem {
  label: string;
  scale: number;
  finishId?: number;
}

export function loadSavedScales(): SavedScaleItem[] {
  try {
    const raw = localStorage.getItem(SCALES_STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

export function saveScalesList(list: SavedScaleItem[]) {
  try {
    localStorage.setItem(SCALES_STORAGE_KEY, JSON.stringify(list));
  } catch { /* ignore */ }
}

export default function FinishPicker({
  open, onClose, onPick, title = "Assign finish", initialScale = 1, initialFinishId = null,
}: {
  open: boolean;
  onClose: () => void;
  onPick: (f: Finish, scale: number) => void;
  title?: string;
  initialScale?: number;
  initialFinishId?: number | null;
}) {
  const { data } = usePoll<Finish[]>(() => api.get("/api/finishes"), 60000, open);
  const [cat, setCat] = useState<"all" | Category>("all");
  const [q, setQ] = useState("");
  const [scale, setScale] = useState<number>(initialScale || 1);
  const [scaleDraft, setScaleDraft] = useState<string>(String(initialScale || 1));
  const [selectedFinish, setSelectedFinish] = useState<Finish | null>(null);
  const [savedScales, setSavedScales] = useState<SavedScaleItem[]>(() => loadSavedScales());
  const [customLabel, setCustomLabel] = useState("");

  useEffect(() => {
    if (!open) return;
    const s = initialScale && initialScale > 0 ? initialScale : 1;
    setScale(s);
    setScaleDraft(String(s));
    setSavedScales(loadSavedScales());
    setSelectedFinish(null);
  }, [open, initialScale, initialFinishId]);

  const list = (data || []).filter((f) =>
    (cat === "all" || f.category === cat) &&
    (!q || `${f.name} ${f.tags}`.toLowerCase().includes(q.toLowerCase())));

  const activeFinish = selectedFinish || (initialFinishId ? list.find((f) => f.id === initialFinishId) : null) || list[0] || null;

  const updateScale = (next: number) => {
    if (!Number.isFinite(next) || next <= 0) return;
    const rounded = Math.round(next * 1000) / 1000;
    setScale(rounded);
    setScaleDraft(String(rounded));
  };

  const handleSaveScale = () => {
    const effW = activeFinish ? Math.round(activeFinish.swatch_width_in * scale * 100) / 100 : null;
    const effH = activeFinish ? Math.round(activeFinish.swatch_height_in * scale * 100) / 100 : null;
    const label = customLabel.trim() || (effW && effH ? `${effW}×${effH}" (${scale}×)` : `${scale}×`);
    const next = [...savedScales.filter((s) => !(s.label === label && s.scale === scale)), { label, scale, finishId: activeFinish?.id }];
    setSavedScales(next);
    saveScalesList(next);
    setCustomLabel("");
    toast(`Saved scale "${label}"`);
  };

  const handleDeleteScale = (idx: number) => {
    const next = savedScales.filter((_, i) => i !== idx);
    setSavedScales(next);
    saveScalesList(next);
  };

  return (
    <Modal open={open} onClose={onClose} title={title} wide>
      {/* Custom per-assignment scale & saved scales bar */}
      <div className="mb-4 rounded-xl border border-zinc-800 bg-zinc-900/70 p-3">
        <div className="flex flex-wrap items-center gap-3">
          <div className="text-xs font-medium text-zinc-300">Assignment scale:</div>
          <label className="flex items-center gap-1.5 text-xs text-zinc-400">
            <span>Multiplier ×</span>
            <input
              type="number"
              min="0.01"
              step="0.1"
              value={scaleDraft}
              onChange={(e) => {
                setScaleDraft(e.target.value);
                const n = Number(e.target.value);
                if (Number.isFinite(n) && n > 0) setScale(Math.round(n * 1000) / 1000);
              }}
              className="w-20 rounded border border-zinc-700 bg-zinc-950 px-2 py-1 text-xs text-amber-300 outline-none focus:border-amber-500"
            />
          </label>
          {activeFinish && (
            <div className="flex items-center gap-1.5 text-xs text-zinc-400">
              <span>Tile size (in):</span>
              <input
                type="number"
                min="0.1"
                step="0.5"
                value={Math.round(activeFinish.swatch_width_in * scale * 100) / 100}
                onChange={(e) => {
                  const w = Number(e.target.value);
                  if (Number.isFinite(w) && w > 0 && activeFinish.swatch_width_in > 0) {
                    updateScale(w / activeFinish.swatch_width_in);
                  }
                }}
                className="w-20 rounded border border-zinc-700 bg-zinc-950 px-2 py-1 text-xs text-zinc-200 outline-none focus:border-amber-500"
                title="Target width in inches for this assignment (scales proportionally)"
              />
              <span>×</span>
              <span className="rounded border border-zinc-800 bg-zinc-950 px-2 py-1 text-xs text-zinc-400">
                {Math.round(activeFinish.swatch_height_in * scale * 100) / 100}&quot;
              </span>
              <span className="text-[11px] text-zinc-500">
                (base {activeFinish.swatch_width_in}×{activeFinish.swatch_height_in}&quot;)
              </span>
            </div>
          )}
          <div className="ml-auto flex items-center gap-1">
            {[0.25, 0.5, 1, 2, 4].map((preset) => (
              <button
                key={preset}
                type="button"
                onClick={() => updateScale(preset)}
                className={`rounded border px-2 py-1 text-[11px] ${scale === preset ? "border-amber-500/60 bg-amber-500/15 text-amber-300" : "border-zinc-700 bg-zinc-950 text-zinc-400 hover:text-zinc-200"}`}
              >
                {preset}×
              </button>
            ))}
          </div>
        </div>

        {/* Saved scales */}
        <div className="mt-2.5 flex flex-wrap items-center gap-1.5 border-t border-zinc-800/80 pt-2.5">
          <span className="text-[11px] text-zinc-500">Saved scales:</span>
          {savedScales.map((item, idx) => (
            <span key={`${item.label}-${idx}`} className="inline-flex items-center rounded border border-zinc-700 bg-zinc-950 text-[11px] text-zinc-300">
              <button type="button" onClick={() => updateScale(item.scale)} className="px-2 py-0.5 hover:text-amber-300">
                {item.label}
              </button>
              <button type="button" onClick={() => handleDeleteScale(idx)} className="border-l border-zinc-800 px-1.5 py-0.5 text-zinc-500 hover:text-red-400" title="Remove saved scale">
                ×
              </button>
            </span>
          ))}
          <div className="ml-auto flex items-center gap-1">
            <input
              value={customLabel}
              onChange={(e) => setCustomLabel(e.target.value)}
              placeholder="Label (optional)"
              className="w-28 rounded border border-zinc-700 bg-zinc-950 px-2 py-0.5 text-[11px] text-zinc-200 outline-none focus:border-amber-500"
            />
            <button
              type="button"
              onClick={handleSaveScale}
              className="rounded border border-amber-500/40 bg-amber-500/10 px-2 py-0.5 text-[11px] text-amber-300 hover:bg-amber-500/20"
            >
              + Save scale ({scale}×)
            </button>
          </div>
        </div>
      </div>

      <div className="mb-4 flex flex-wrap items-center gap-2">
        {CATS.map((c) => (
          <button key={c} onClick={() => setCat(c)}
            className={`rounded-full border px-3 py-1 text-xs ${cat === c ? "border-amber-500/50 bg-amber-500/15 text-amber-300" : "border-zinc-700 text-zinc-400 hover:border-zinc-500 hover:text-zinc-200"}`}>
            {c === "all" ? "All" : CATEGORY_LABEL[c]}
          </button>
        ))}
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search finishes…"
          className="ml-auto w-52 rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-1.5 text-sm text-zinc-200 placeholder-zinc-500 outline-none focus:border-amber-500/60" />
      </div>
      {list.length === 0 && <p className="py-10 text-center text-sm text-zinc-500">No finishes match.</p>}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {list.map((f) => {
          const effW = Math.round(f.swatch_width_in * scale * 100) / 100;
          const effH = Math.round(f.swatch_height_in * scale * 100) / 100;
          return (
            <button
              key={f.id}
              onMouseEnter={() => setSelectedFinish(f)}
              onClick={() => { onPick(f, scale); onClose(); }}
              className="group overflow-hidden rounded-xl border border-zinc-800 bg-zinc-950 text-left transition-colors hover:border-amber-500/60"
            >
              <div className="aspect-square w-full overflow-hidden">
                <img src={f.thumb_url} alt={f.name} className="h-full w-full object-cover transition-transform group-hover:scale-105" />
              </div>
              <div className="p-2.5">
                <div className="truncate text-sm text-zinc-200">{f.name}</div>
                <div className="mt-1 flex items-center justify-between gap-1">
                  <span className={`rounded border px-1.5 py-0.5 text-[10px] ${CATEGORY_COLOR[f.category]}`}>{CATEGORY_LABEL[f.category]}</span>
                  <span className="text-[10px] text-amber-300/90" title={`Base: ${f.swatch_width_in}×${f.swatch_height_in}" · Applied at ${scale}×`}>
                    {effW}×{effH}&quot; ({scale}×)
                  </span>
                </div>
              </div>
            </button>
          );
        })}
      </div>
    </Modal>
  );
}
