import { useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, fmtDate, toast } from "../api";
import { usePoll } from "../hooks";
import Viewer3D, { type ViewerItem } from "../components/Viewer3D";
import FinishPicker from "../components/FinishPicker";
import JobProgress, { StatusChip } from "../components/JobProgress";
import RenderDialog from "../components/RenderDialog";
import Modal from "../components/Modal";
import type { Assignment, Finish, ModelDetail, Preset, RenderResult, Suggestion } from "../types";

type Target = { kind: "layer" | "block" | "part"; name: string };

export default function ModelWorkspace() {
  const { id } = useParams();
  const modelId = Number(id);
  const { data: model, refresh } = usePoll<ModelDetail>(() => api.get(`/api/models/${modelId}`), 2000);
  const { data: renders, refresh: refreshRenders } = usePoll<RenderResult[]>(
    () => api.get(`/api/renders?model_id=${modelId}`), 3000);
  const [tab, setTab] = useState<"structure" | "assignments" | "renders">("structure");
  const [picker, setPicker] = useState<Target | null>(null);
  const [autoOpen, setAutoOpen] = useState(false);
  const [applyOpen, setApplyOpen] = useState(false);
  const [saveOpen, setSaveOpen] = useState(false);
  const [presetName, setPresetName] = useState("");
  const [renderOpen, setRenderOpen] = useState(false);
  const [selected, setSelected] = useState<Set<string>>(new Set());

  const assign = async (t: Target, finishId: number | null, scale = 1) => {
    try {
      await api.post(`/api/models/${modelId}/assignments`, {
        target_kind: t.kind, target_name: t.name, finish_id: finishId, scale_multiplier: scale,
      });
      await refresh();
    } catch (e) {
      toast(e instanceof Error ? e.message : "assignment failed", "err");
    }
  };

  const items: ViewerItem[] = useMemo(() => {
    if (!model?.structure) return [];
    const byKind = { layer: new Map<string, Assignment>(), block: new Map<string, Assignment>(), part: new Map<string, Assignment>() };
    for (const a of model.assignments) byKind[a.target_kind]?.set(a.target_name, a);
    return model.structure.parts.map((p) => {
      const a = byKind.part.get(p.name) || (p.block ? byKind.block.get(p.block) : undefined) || byKind.layer.get(p.layer);
      return {
        id: p.id,
        name: p.name,
        bbox: p.bbox,
        rbe: p.requires_block_edit,
        color: model.structure!.layers.find((l) => l.name === p.layer)?.color || "#71717a",
        finish: a?.finish ? {
          url: a.finish.image_url,
          sw_w: a.finish.swatch_width_in,
          sw_h: a.finish.swatch_height_in,
          scale: a.scale_multiplier || 1,
          metallic: a.finish.category === "product_finish",
        } : null,
      };
    });
  }, [model]);

  const assignFor = (t: Target): Assignment | undefined =>
    model?.assignments.find((a) => a.target_kind === t.kind && a.target_name === t.name);

  const analyzeJob = model?.jobs?.find((j) => j.kind === "analyze");
  const activeJobs = (model?.jobs || []).filter((j) => j.status === "queued" || j.status === "running");

  if (!model) return <p className="p-10 text-sm text-zinc-500">Loading model…</p>;

  return (
    <div className="flex h-full flex-col">
      {/* header */}
      <header className="flex items-center gap-4 border-b border-zinc-800 px-6 py-4">
        <Link to="/models" className="rounded-lg border border-zinc-800 p-2 text-zinc-400 hover:bg-zinc-900 hover:text-zinc-200">
          <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="2"><path d="M15 18l-6-6 6-6" /></svg>
        </Link>
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <h1 className="truncate text-base font-semibold text-zinc-100">{model.name}</h1>
            <StatusChip status={model.status} />
          </div>
          <p className="mt-0.5 text-xs text-zinc-500">
            {model.structure ? `${model.structure.parts.length} parts · ${model.structure.layers.length} layers · ${model.structure.blocks.length} block defs · units: ${model.units}` : model.original_name}
          </p>
        </div>
        <div className="ml-auto flex items-center gap-2">
          <button onClick={() => setAutoOpen(true)} disabled={model.status !== "ready"}
            className="rounded-lg border border-zinc-700 px-3 py-2 text-sm text-zinc-300 hover:bg-zinc-800 disabled:opacity-40">
            Auto-match
          </button>
          <button onClick={() => setApplyOpen(true)} disabled={model.status !== "ready"}
            className="rounded-lg border border-zinc-700 px-3 py-2 text-sm text-zinc-300 hover:bg-zinc-800 disabled:opacity-40">
            Apply preset
          </button>
          <button onClick={() => { setPresetName(`${model.name} preset`); setSaveOpen(true); }}
            disabled={!model.assignments.length}
            className="rounded-lg border border-zinc-700 px-3 py-2 text-sm text-zinc-300 hover:bg-zinc-800 disabled:opacity-40">
            Save preset
          </button>
          <button onClick={() => setRenderOpen(true)} disabled={model.status !== "ready"}
            className="rounded-lg bg-amber-500 px-4 py-2 text-sm font-medium text-zinc-950 hover:bg-amber-400 disabled:opacity-40">
            Render
          </button>
        </div>
      </header>

      {/* body */}
      {model.status !== "ready" ? (
        <div className="mx-auto w-full max-w-xl px-6 py-16">
          {model.status === "failed" ? (
            <div className="rounded-xl border border-red-900/60 bg-red-950/30 p-6 text-center">
              <p className="text-sm text-red-300">Analysis failed.</p>
              <button onClick={async () => { await api.post(`/api/models/${modelId}/reanalyze`); refresh(); }}
                className="mt-4 rounded-lg bg-amber-500 px-4 py-2 text-sm font-medium text-zinc-950">Re-analyze</button>
            </div>
          ) : analyzeJob ? (
            <JobProgress job={analyzeJob} />
          ) : (
            <p className="text-center text-sm text-zinc-500">Preparing…</p>
          )}
        </div>
      ) : (
        <div className="grid min-h-0 flex-1 grid-cols-1 xl:grid-cols-[1fr_420px]">
          {/* viewer */}
          <div className="relative min-h-[420px] border-b border-zinc-800 bg-gradient-to-b from-zinc-900 to-zinc-950 xl:border-b-0 xl:border-r">
            <Viewer3D items={items} selected={selected}
              onSelect={(pid) => setSelected(pid ? new Set([pid]) : new Set())} />
            <div className="pointer-events-none absolute left-4 top-4 rounded-lg border border-zinc-800/80 bg-zinc-950/70 px-3 py-2 text-[11px] text-zinc-400 backdrop-blur">
              Drag to orbit · scroll to zoom · click a part to select
              <span className="ml-2 text-cyan-400">cyan outline = inside block (BlockEdit)</span>
            </div>
          </div>

          {/* right panel */}
          <div className="flex min-h-0 flex-col">
            <div className="flex border-b border-zinc-800">
              {(["structure", "assignments", "renders"] as const).map((t) => (
                <button key={t} onClick={() => setTab(t)}
                  className={`flex-1 px-4 py-2.5 text-sm capitalize ${tab === t ? "border-b-2 border-amber-500 text-amber-300" : "text-zinc-500 hover:text-zinc-300"}`}>
                  {t}{t === "renders" && renders?.length ? ` (${renders.length})` : ""}
                </button>
              ))}
            </div>
            <div className="min-h-0 flex-1 overflow-y-auto p-4">
              {tab === "structure" && model.structure && (
                <div className="space-y-5">
                  <section>
                    <h3 className="mb-2 text-xs uppercase tracking-wide text-zinc-500">Layers</h3>
                    <div className="space-y-1.5">
                      {model.structure.layers.map((l) => {
                        const a = assignFor({ kind: "layer", name: l.name });
                        return (
                          <div key={l.name} className="flex items-center gap-2 rounded-lg border border-zinc-800 bg-zinc-900/50 px-3 py-2">
                            <button className="flex min-w-0 flex-1 items-center gap-2 text-left"
                              onClick={() => setSelected(new Set(model.structure!.parts.filter((p) => p.layer === l.name).map((p) => p.id)))}>
                              <span className="h-3 w-3 shrink-0 rounded-sm" style={{ background: l.color }} />
                              <span className="truncate text-sm text-zinc-200">{l.name}</span>
                              <span className="ml-1 text-[11px] text-zinc-600">{l.part_count}</span>
                            </button>
                            {a?.finish ? (
                              <>
                                <img src={a.finish.thumb_url} alt="" className="h-6 w-6 rounded object-cover" />
                                <span className="max-w-[110px] truncate text-xs text-zinc-400">{a.finish.name}</span>
                                <button onClick={() => assign({ kind: "layer", name: l.name }, null)}
                                  className="rounded p-1 text-zinc-600 hover:bg-zinc-800 hover:text-red-400" title="Clear">✕</button>
                              </>
                            ) : (
                              <span className="text-[11px] text-zinc-600">unassigned</span>
                            )}
                            <button onClick={() => setPicker({ kind: "layer", name: l.name })}
                              className="rounded-lg border border-zinc-700 px-2 py-1 text-[11px] text-zinc-300 hover:bg-zinc-800">
                              {a ? "Change" : "Assign"}
                            </button>
                          </div>
                        );
                      })}
                    </div>
                  </section>
                  {model.structure.blocks.length > 0 && (
                    <section>
                      <h3 className="mb-2 text-xs uppercase tracking-wide text-zinc-500">Block definitions</h3>
                      <div className="space-y-3">
                        {model.structure.blocks.map((b) => {
                          const a = assignFor({ kind: "block", name: b.name });
                          return (
                            <div key={b.name} className="rounded-lg border border-cyan-900/50 bg-cyan-950/10 p-3">
                              <div className="flex items-center gap-2">
                                <svg viewBox="0 0 24 24" className="h-4 w-4 text-cyan-400" fill="currentColor"><path d="M12 2 3 7v10l9 5 9-5V7l-9-5Zm0 2.3 6.7 3.7L12 11.7 5.3 8 12 4.3Z" /></svg>
                                <span className="text-sm text-zinc-200">{b.name}</span>
                                <span className="text-[11px] text-zinc-500">×{b.instance_count} instances</span>
                                <span className="ml-auto rounded border border-cyan-700/40 bg-cyan-500/10 px-1.5 py-0.5 text-[10px] text-cyan-300">BlockEdit</span>
                              </div>
                              <div className="mt-2 flex items-center gap-2">
                                {a?.finish ? (
                                  <><img src={a.finish.thumb_url} alt="" className="h-6 w-6 rounded object-cover" />
                                    <span className="text-xs text-zinc-400">{a.finish.name}</span>
                                    <button onClick={() => assign({ kind: "block", name: b.name }, null)} className="text-zinc-600 hover:text-red-400">✕</button></>
                                ) : <span className="text-[11px] text-zinc-600">inherits layer finishes</span>}
                                <button onClick={() => setPicker({ kind: "block", name: b.name })}
                                  className="ml-auto rounded-lg border border-zinc-700 px-2 py-1 text-[11px] text-zinc-300 hover:bg-zinc-800">
                                  {a ? "Change" : "Assign whole block"}
                                </button>
                              </div>
                              <ul className="mt-2 space-y-1 border-t border-zinc-800/60 pt-2">
                                {model.structure!.parts.filter((p) => p.block === b.name).map((p) => {
                                  const pa = assignFor({ kind: "part", name: p.name });
                                  return (
                                    <li key={p.id} className="flex items-center gap-2 text-xs text-zinc-400">
                                      <button className="truncate hover:text-zinc-200" onClick={() => setSelected(new Set([p.id]))}>{p.name}</button>
                                      <span className="text-[10px] text-zinc-600">{p.layer}</span>
                                      <span className="ml-auto flex items-center gap-1">
                                        {pa?.finish && <img src={pa.finish.thumb_url} alt="" className="h-4 w-4 rounded object-cover" />}
                                        <button onClick={() => setPicker({ kind: "part", name: p.name })}
                                          className="rounded border border-zinc-800 px-1.5 py-0.5 text-[10px] text-zinc-400 hover:bg-zinc-800">
                                          {pa ? "override" : "override"}
                                        </button>
                                        {pa && <button onClick={() => assign({ kind: "part", name: p.name }, null)} className="text-zinc-600 hover:text-red-400">✕</button>}
                                      </span>
                                    </li>
                                  );
                                })}
                              </ul>
                            </div>
                          );
                        })}
                      </div>
                    </section>
                  )}
                </div>
              )}

              {tab === "assignments" && (
                <div className="space-y-1.5">
                  {model.assignments.length === 0 && (
                    <p className="py-10 text-center text-sm text-zinc-500">
                      No finishes mapped yet.<br />
                      <button className="mt-2 text-amber-400 hover:underline" onClick={() => setAutoOpen(true)}>Run auto-match</button> or assign per layer in the Structure tab.
                    </p>
                  )}
                  {model.assignments.map((a) => (
                    <div key={a.id} className="flex items-center gap-3 rounded-lg border border-zinc-800 bg-zinc-900/50 px-3 py-2">
                      <span className={`rounded border px-1.5 py-0.5 text-[10px] uppercase ${a.target_kind === "layer" ? "border-zinc-700 text-zinc-400" : a.target_kind === "block" ? "border-cyan-700/50 text-cyan-300" : "border-amber-700/50 text-amber-300"}`}>
                        {a.target_kind}
                      </span>
                      <span className="min-w-0 flex-1 truncate text-sm text-zinc-200">{a.target_name}</span>
                      {a.finish && <img src={a.finish.thumb_url} alt="" className="h-7 w-7 rounded object-cover" />}
                      <span className="w-32 truncate text-xs text-zinc-400">{a.finish?.name}</span>
                      <button onClick={() => setPicker({ kind: a.target_kind, name: a.target_name })}
                        className="rounded-lg border border-zinc-700 px-2 py-1 text-[11px] text-zinc-300 hover:bg-zinc-800">Change</button>
                      <button onClick={() => assign({ kind: a.target_kind, name: a.target_name }, null)}
                        className="rounded p-1 text-zinc-600 hover:bg-zinc-800 hover:text-red-400">✕</button>
                    </div>
                  ))}
                </div>
              )}

              {tab === "renders" && (
                <div className="space-y-3">
                  {activeJobs.length > 0 && activeJobs.map((j) => <JobProgress key={j.id} job={j} />)}
                  {(renders || []).length === 0 && activeJobs.length === 0 && (
                    <p className="py-10 text-center text-sm text-zinc-500">No renders yet — hit Render to queue one.</p>
                  )}
                  {(renders || []).map((r) => (
                    <a key={r.id} href={r.image_url} target="_blank" rel="noreferrer"
                      className="block overflow-hidden rounded-lg border border-zinc-800 bg-zinc-950 hover:border-amber-500/50">
                      <img src={r.image_url} alt="" className="aspect-video w-full object-cover" />
                      <div className="flex items-center gap-2 p-2.5 text-[11px] text-zinc-500">
                        <span className="text-zinc-300">{r.quality} · {r.camera}</span>
                        <span>{r.width}×{r.height}</span>
                        <span className="ml-auto">{fmtDate(r.created_at)}</span>
                      </div>
                    </a>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* modals */}
      <FinishPicker open={!!picker} onClose={() => setPicker(null)}
        title={picker ? `Assign finish → ${picker.kind}: ${picker.name}` : ""}
        onPick={(f: Finish) => picker && assign(picker, f.id)} />
      <AutoMatchModal open={autoOpen} onClose={() => setAutoOpen(false)} modelId={modelId} onApplied={refresh} />
      <ApplyPresetModal open={applyOpen} onClose={() => setApplyOpen(false)} modelId={modelId} onApplied={refresh} />
      <Modal open={saveOpen} onClose={() => setSaveOpen(false)} title="Save mapping as preset">
        <label className="mb-1.5 block text-xs uppercase tracking-wide text-zinc-500">Preset name</label>
        <input value={presetName} onChange={(e) => setPresetName(e.target.value)}
          className="w-full rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm text-zinc-200 outline-none focus:border-amber-500/60" />
        <p className="mt-3 text-xs leading-relaxed text-zinc-500">
          Rules are generated from the current layer assignments using each layer's most distinctive
          token, so the preset also matches similar future drawings.
        </p>
        <div className="mt-4 flex justify-end gap-2">
          <button onClick={() => setSaveOpen(false)} className="rounded-lg border border-zinc-700 px-4 py-2 text-sm text-zinc-300 hover:bg-zinc-800">Cancel</button>
          <button onClick={async () => {
            try {
              await api.post("/api/presets/from-model", { model_id: modelId, name: presetName });
              toast("Preset saved");
              setSaveOpen(false);
            } catch (e) { toast(e instanceof Error ? e.message : "failed", "err"); }
          }} className="rounded-lg bg-amber-500 px-4 py-2 text-sm font-medium text-zinc-950 hover:bg-amber-400">Save preset</button>
        </div>
      </Modal>
      <RenderDialog open={renderOpen} onClose={() => setRenderOpen(false)} modelId={modelId}
        onDone={() => { refreshRenders(); setTab("renders"); }} />
    </div>
  );
}

function AutoMatchModal({ open, onClose, modelId, onApplied }: {
  open: boolean; onClose: () => void; modelId: number; onApplied: () => void;
}) {
  const { data } = usePoll<Suggestion[]>(() => api.get(`/api/models/${modelId}/automatch?min_score=0.3`), 30000, open);
  const [checked, setChecked] = useState<Set<string> | null>(null);
  const sugg = data || [];
  const sel = checked || new Set(sugg.filter((s) => s.score >= 0.45).map((s) => `${s.target_kind}:${s.target_name}`));
  return (
    <Modal open={open} onClose={onClose} title="Auto-match finishes by name" wide>
      {sugg.length === 0 && <p className="py-8 text-center text-sm text-zinc-500">No confident matches — assign manually or add finishes to the library.</p>}
      <div className="space-y-1.5">
        {sugg.map((s) => {
          const key = `${s.target_kind}:${s.target_name}`;
          return (
            <label key={key} className="flex cursor-pointer items-center gap-3 rounded-lg border border-zinc-800 bg-zinc-950 px-3 py-2 hover:border-zinc-700">
              <input type="checkbox" checked={sel.has(key)}
                onChange={(e) => {
                  const next = new Set(sel);
                  if (e.target.checked) next.add(key); else next.delete(key);
                  setChecked(next);
                }} />
              <span className="w-40 truncate text-sm text-zinc-200">{s.target_name}</span>
              <svg viewBox="0 0 24 24" className="h-3.5 w-3.5 text-zinc-600" fill="none" stroke="currentColor" strokeWidth="2"><path d="M5 12h14m-6-6 6 6-6 6" /></svg>
              <img src={s.finish.thumb_url} alt="" className="h-7 w-7 rounded object-cover" />
              <span className="flex-1 truncate text-sm text-zinc-300">{s.finish.name}</span>
              <span className={`rounded px-1.5 py-0.5 text-[11px] ${s.score >= 0.7 ? "bg-emerald-500/15 text-emerald-300" : s.score >= 0.45 ? "bg-amber-500/15 text-amber-300" : "bg-zinc-700/30 text-zinc-400"}`}>
                {Math.round(s.score * 100)}%
              </span>
            </label>
          );
        })}
      </div>
      <div className="mt-4 flex justify-end gap-2">
        <button onClick={onClose} className="rounded-lg border border-zinc-700 px-4 py-2 text-sm text-zinc-300 hover:bg-zinc-800">Cancel</button>
        <button onClick={async () => {
          let n = 0;
          for (const s of sugg) {
            if (!sel.has(`${s.target_kind}:${s.target_name}`)) continue;
            await api.post(`/api/models/${modelId}/assignments`, { target_kind: s.target_kind, target_name: s.target_name, finish_id: s.finish_id });
            n++;
          }
          toast(`Applied ${n} matches`);
          onApplied();
          onClose();
        }} className="rounded-lg bg-amber-500 px-4 py-2 text-sm font-medium text-zinc-950 hover:bg-amber-400">Apply selected</button>
      </div>
    </Modal>
  );
}

function ApplyPresetModal({ open, onClose, modelId, onApplied }: {
  open: boolean; onClose: () => void; modelId: number; onApplied: () => void;
}) {
  const { data } = usePoll<Preset[]>(() => api.get("/api/presets"), 30000, open);
  const [pid, setPid] = useState<number | null>(null);
  return (
    <Modal open={open} onClose={onClose} title="Apply a mapping preset">
      <div className="space-y-1.5">
        {(data || []).length === 0 && <p className="py-6 text-center text-sm text-zinc-500">No presets yet — save one from a mapped model.</p>}
        {(data || []).map((p) => (
          <label key={p.id} className="flex cursor-pointer items-center gap-3 rounded-lg border border-zinc-800 bg-zinc-950 px-3 py-2.5 hover:border-zinc-700">
            <input type="radio" name="preset" checked={pid === p.id} onChange={() => setPid(p.id)} />
            <span className="flex-1">
              <span className="block text-sm text-zinc-200">{p.name}</span>
              <span className="block text-[11px] text-zinc-500">{p.rule_count} rules{p.description ? ` — ${p.description}` : ""}</span>
            </span>
          </label>
        ))}
      </div>
      <div className="mt-4 flex justify-end gap-2">
        <button onClick={onClose} className="rounded-lg border border-zinc-700 px-4 py-2 text-sm text-zinc-300 hover:bg-zinc-800">Cancel</button>
        <button disabled={pid == null} onClick={async () => {
          try {
            const r = await api.post(`/api/models/${modelId}/presets/${pid}/apply`, { overwrite: true });
            toast(`Preset applied — ${r.applied} targets matched`);
            onApplied();
            onClose();
          } catch (e) { toast(e instanceof Error ? e.message : "failed", "err"); }
        }} className="rounded-lg bg-amber-500 px-4 py-2 text-sm font-medium text-zinc-950 hover:bg-amber-400 disabled:opacity-40">Apply</button>
      </div>
    </Modal>
  );
}
