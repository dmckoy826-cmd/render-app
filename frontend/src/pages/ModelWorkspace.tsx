import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, fmtDate, toast } from "../api";
import { usePoll } from "../hooks";
import Viewer3D, { type ViewerItem } from "../components/Viewer3D";
import FinishPicker from "../components/FinishPicker";
import FinishSettingsModal, {
  formatTransformSummary,
  type FinishTransformSettings,
} from "../components/FinishSettingsModal";
import JobProgress, { StatusChip } from "../components/JobProgress";
import RenderDialog from "../components/RenderDialog";
import Modal from "../components/Modal";
import type { Assignment, CameraPose, Finish, ModelDetail, Part, Preset, RenderResult, SavedCameraView, Suggestion } from "../types";

type Target = { kind: "layer" | "block" | "part"; name: string; label?: string };

// Older analyses identified child sublayers as SKU layers. Treat their full paths
// as belonging to the root SKU layer, without forcing another expensive analysis.
const skuRoot = (name: string) => name.split("::", 1)[0];

function AssignmentTransformButton({
  assignment,
  onOpen,
}: {
  assignment: Assignment;
  onOpen: () => void;
}) {
  const f = assignment.finish;
  const scale = assignment.scale_multiplier || 1;
  const effW = f ? Math.round(f.swatch_width_in * scale * 100) / 100 : null;
  const effH = f ? Math.round(f.swatch_height_in * scale * 100) / 100 : null;
  return (
    <button
      type="button"
      onClick={onOpen}
      className="inline-flex items-center gap-1 rounded border border-amber-500/40 bg-amber-500/10 px-2 py-0.5 text-[11px] font-mono text-amber-300 hover:bg-amber-500/20"
      title={
        effW && effH
          ? `Adjust Scale (${effW}×${effH}"), Rotation (0–90°), & Seam Offset`
          : "Adjust Scale, Rotation (0–90°), & Seam Offset"
      }
    >
      <span>⚙</span>
      <span>{formatTransformSummary(assignment)}</span>
    </button>
  );
}

export default function ModelWorkspace() {
  const { id } = useParams();
  const modelId = Number(id);
  const { data: model, refresh } = usePoll<ModelDetail>(() => api.get(`/api/models/${modelId}`), 2000);
  const { data: renders, refresh: refreshRenders } = usePoll<RenderResult[]>(
    () => api.get(`/api/renders?model_id=${modelId}`), 3000);
  const [tab, setTab] = useState<"structure" | "assignments" | "renders">("structure");
  const [picker, setPicker] = useState<Target | null>(null);
  const [transformModal, setTransformModal] = useState<{
    target: Target;
    assignment: Assignment;
  } | null>(null);
  const [autoOpen, setAutoOpen] = useState(false);
  const [applyOpen, setApplyOpen] = useState(false);
  const [saveOpen, setSaveOpen] = useState(false);
  const [presetName, setPresetName] = useState("");
  const [renderOpen, setRenderOpen] = useState(false);
  const [renderMode, setRenderMode] = useState<"single" | "batch">("single");
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [partSearch, setPartSearch] = useState("");
  const [partLimit, setPartLimit] = useState(100);
  const [cameraPose, setCameraPose] = useState<CameraPose | null>(null);
  const viewsKey = `ff_saved_views_${modelId}`;
  const [savedViews, setSavedViews] = useState<SavedCameraView[]>([]);

  useEffect(() => {
    try {
      const raw = localStorage.getItem(viewsKey);
      setSavedViews(raw ? JSON.parse(raw) : []);
    } catch {
      setSavedViews([]);
    }
  }, [viewsKey]);

  const handleSaveView = (name: string, pose: CameraPose) => {
    const next = [...savedViews.filter((v) => v.name !== name), { name, pose }];
    setSavedViews(next);
    try { localStorage.setItem(viewsKey, JSON.stringify(next)); } catch { /* ignore */ }
    toast(`Saved camera view "${name}"`);
  };

  const handleDeleteView = (name: string) => {
    const next = savedViews.filter((v) => v.name !== name);
    setSavedViews(next);
    try { localStorage.setItem(viewsKey, JSON.stringify(next)); } catch { /* ignore */ }
  };

  const assign = async (
    t: Target,
    finishId: number | null,
    scale = 1,
    rotationDeg = 0,
    offsetUIn = 0,
    offsetVIn = 0
  ) => {
    try {
      await api.post(`/api/models/${modelId}/assignments`, {
        target_kind: t.kind,
        target_name: t.name,
        finish_id: finishId,
        scale_multiplier: scale,
        rotation_deg: rotationDeg,
        offset_u_in: offsetUIn,
        offset_v_in: offsetVIn,
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
    const stableTargets = model.structure.target_schema === "rhino-geometry-v1";
    const colors = new Map(model.structure.layers.map((layer) => [layer.name, layer.color]));
    return model.structure.parts.map((p) => {
      const direct = byKind.part.get(stableTargets ? p.id : p.name);
      const paths = p.block_paths?.length ? p.block_paths : [p.block ? [p.block] : []];
      const resolved = paths.map((path) => direct || [...path].reverse().map((b) => byKind.block.get(b)).find(Boolean) || byKind.layer.get(p.layer));
      const values = new Set(resolved.map((a) => a ? `${a.finish_id}:${a.scale_multiplier}:${a.rotation_deg || 0}:${a.offset_u_in || 0}:${a.offset_v_in || 0}` : "unassigned"));
      const conflict = values.size > 1;
      const a = conflict ? undefined : resolved[0];
      const rawSkuLayers = p.sku_layers || model.structure!.sku_layers
        ?.filter((sku) => sku.part_layers.includes(p.layer)).map((sku) => sku.name) || [];
      const skuLayers = [...new Set(rawSkuLayers.map(skuRoot))];
      return {
        id: p.id, name: p.name, layer: p.layer, skuLayers, bbox: p.bbox, rbe: p.requires_block_edit, conflict,
        color: colors.get(p.layer) || "#71717a",
        finish: a?.finish ? {
          url: a.finish.image_url, sw_w: a.finish.swatch_width_in, sw_h: a.finish.swatch_height_in,
          scale: a.scale_multiplier || 1,
          rotation_deg: a.rotation_deg || 0,
          offset_u_in: a.offset_u_in || 0,
          offset_v_in: a.offset_v_in || 0,
          metallic: false,  // category alone does not imply a metal shader
        } : null,
      };
    });
  }, [model]);
  // Polling returns fresh objects every two seconds. Do not rebuild potentially large
  // Three.js meshes or reset the camera unless geometry/material data actually changes.
  const stableItemsRef = useRef<{ key: string; value: ViewerItem[] }>({ key: "", value: [] });
  const itemsKey = JSON.stringify(items);
  if (stableItemsRef.current.key !== itemsKey) stableItemsRef.current = { key: itemsKey, value: items };
  const stableItems = stableItemsRef.current.value;
  const partTarget = (p: { id: string; name: string }) =>
    model?.structure?.target_schema === "rhino-geometry-v1" ? p.id : p.name;

  const assignFor = (t: Target): Assignment | undefined =>
    model?.assignments.find((a) => a.target_kind === t.kind && a.target_name === t.name);

  const partById = useMemo(() => new Map((model?.structure?.parts || []).map((part) => [part.id, part])), [model?.structure]);
  const matchingParts = useMemo(() => {
    const query = partSearch.trim().toLowerCase();
    const parts = model?.structure?.parts || [];
    return query ? parts.filter((p) => `${p.name} ${p.layer} ${p.block || ""} ${p.id}`.toLowerCase().includes(query)) : parts;
  }, [model?.structure, partSearch]);
  const analyzeJob = model?.jobs?.find((j) => j.kind === "analyze");
  const activeJobs = (model?.jobs || []).filter((j) => j.status === "queued" || j.status === "running");

  if (!model) return <p className="p-10 text-sm text-zinc-500">Loading model…</p>;

  return (
    <div className="flex h-full min-h-0 flex-col overflow-hidden">
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
          <button onClick={async () => { await api.post(`/api/models/${modelId}/reanalyze`); refresh(); }}
            disabled={model.status === "uploaded" || model.status === "analyzing"}
            className="rounded-lg border border-zinc-700 px-3 py-2 text-sm text-zinc-300 hover:bg-zinc-800 disabled:opacity-40"
            title="Re-run analysis (e.g. after connecting the Rhino worker)">
            Re-analyze
          </button>
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
          <button onClick={() => { setRenderMode("batch"); setRenderOpen(true); }} disabled={model.status !== "ready"}
            className="rounded-lg border border-amber-500/50 bg-amber-500/10 px-3 py-2 text-sm font-medium text-amber-300 hover:bg-amber-500/20 disabled:opacity-40">
            Batch SKU Render
          </button>
          <button onClick={() => { setRenderMode("single"); setRenderOpen(true); }} disabled={model.status !== "ready"}
            className="rounded-lg bg-amber-500 px-4 py-2 text-sm font-medium text-zinc-950 hover:bg-amber-400 disabled:opacity-40">
            Render
          </button>
        </div>
      </header>

      {/* Analysis source does not imply a mesh preview or a validated V-Ray render. */}
      {model.structure && (() => {
        const a = model.structure!.analyzer || "";
        const rhino = a.startsWith("rhino") && !/fake|stub/i.test(a) && model.structure!.target_schema === "rhino-geometry-v1";
        const synthetic = /fake|stub/i.test(a) && model.structure!.target_schema === "rhino-geometry-v1";
        const parsed = a.startsWith("dxf") || rhino;
        const conflicts = items.filter((item) => item.conflict).length;
        return <div className={`mx-6 mt-4 rounded-lg border px-4 py-3 text-xs leading-relaxed ${parsed
          ? "border-emerald-700/50 bg-emerald-950/20 text-emerald-200"
          : "border-amber-700/50 bg-amber-950/20 text-amber-200"}`}>
          {rhino ? <>Analyzed by <code>{a}</code>. Nested block layers and selectable geometry are included.
            Block edits apply to every reference of the same definition; identical overlapping objects may share a target.</>
            : synthetic ? <>Synthetic test geometry, not imported CAD. Connect the real Rhino worker and re-analyze before rendering.</>
            : a.startsWith("dxf") ? <>DXF structure was parsed, but this viewer only has bounding boxes. Re-analyze with the Rhino worker for a tessellated preview.</>
            : <>Placeholder or older analysis: the viewer shows bounding boxes, not the imported model.
                Connect the Rhino worker and re-analyze before a real render.</>}
          {model.structure!.geometry_warnings?.map((warning) => <div key={warning} className="mt-1 text-amber-300">{warning}</div>)}
          {model.structure!.geometry_status === "partial" && <div className="mt-1 text-zinc-400">
            This warning reports the saved analysis-time tessellation. Preview filters request only enabled SKU/part meshes, but turning layers off cannot change the stored analysis status or recover geometry omitted by the mesh budget. New analyses split that budget fairly across SKU layers.
          </div>}
          {model.structure!.sku_layers?.length && model.structure!.preview_schema !== 2 && <div className="mt-1 text-amber-300">
            Re-analyze this model with the updated Rhino worker to isolate exact geometry per SKU layer. Older previews may combine identical block geometry across SKUs.
          </div>}
          {conflicts > 0 && <div className="mt-1 font-semibold text-amber-300">{conflicts} shared part(s) have conflicting block assignments. The real render will reject them.</div>}
        </div>;
      })()}

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
        <div className="grid min-h-0 flex-1 grid-cols-1 grid-rows-[minmax(360px,1fr)_minmax(0,1fr)] overflow-hidden xl:grid-cols-[minmax(0,1fr)_420px] xl:grid-rows-1">
          {/* viewer */}
          <div className="relative min-h-[360px] min-w-0 overflow-hidden border-b border-zinc-800 bg-gradient-to-b from-zinc-900 to-zinc-950 xl:border-b-0 xl:border-r">
            <Viewer3D items={stableItems} selected={selected} geometryUrl={model.structure?.geometry_url}
              geometryApiUrl={model.structure?.geometry_api_url}
              skuLayerNames={[...new Set((model.structure?.sku_layers || []).map((sku) => skuRoot(sku.name)))]}
              skuGeometryReady={model.structure?.preview_schema === 2}
              partial={model.structure?.geometry_status === "partial"}
              simulatedGeometry={!model.structure?.analyzer?.startsWith("rhino") || /fake|stub/i.test(model.structure?.analyzer || "")}
              onSelect={(pid) => setSelected(pid ? new Set([pid]) : new Set())}
              onCameraChange={setCameraPose}
              savedViews={savedViews}
              onSaveView={handleSaveView}
              onDeleteView={handleDeleteView} />
            <div className="pointer-events-none absolute left-4 top-4 rounded-lg border border-zinc-800/80 bg-zinc-950/70 px-3 py-2 text-[11px] text-zinc-400 backdrop-blur">
              Drag to orbit · scroll to zoom · click a part to select
              <span className="ml-2 text-cyan-400">block targets affect shared definitions</span>
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
                  {selected.size === 1 && (() => {
                    const p = model.structure!.parts.find((part) => selected.has(part.id));
                    if (!p) return null;
                    const target = partTarget(p);
                    const assigned = assignFor({ kind: "part", name: target });
                    return <section className="rounded-lg border border-amber-700/40 bg-amber-950/10 p-3">
                      <div className="text-xs uppercase tracking-wide text-amber-300">Selected part</div>
                      <div className="mt-1 text-sm text-zinc-200">{p.name}</div>
                      <p className="mt-1 text-xs text-zinc-500">{p.layer}{p.block ? ` · in ${p.block} (all references)` : ""}
                        {p.occurrence_count && p.occurrence_count > 1 ? ` · ${p.occurrence_count} occurrences` : ""}
                        {p.matching_objects && p.matching_objects > 1 ? ` · ${p.matching_objects} indistinguishable objects share this target` : ""}
                        {p.renderable === false ? " · linework, not a renderable surface" : ""}
                      </p>
                      <div className="mt-2 flex flex-wrap items-center gap-2">
                        {assigned?.finish && (
                          <AssignmentTransformButton
                            assignment={assigned}
                            onOpen={() =>
                              setTransformModal({
                                target: { kind: "part", name: target, label: p.name },
                                assignment: assigned,
                              })
                            }
                          />
                        )}
                        <button onClick={() => setPicker({ kind: "part", name: target, label: p.name })}
                          className="rounded border border-zinc-700 px-2 py-1 text-xs text-zinc-300 hover:bg-zinc-800">{assigned ? "Change override" : "Assign part override"}</button>
                        {assigned && <button onClick={() => assign({ kind: "part", name: target }, null)} className="text-xs text-zinc-500 hover:text-red-400">Clear override</button>}
                      </div>
                    </section>;
                  })()}
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
                                <span className="max-w-[90px] truncate text-xs text-zinc-400">{a.finish.name}</span>
                                <AssignmentTransformButton
                                  assignment={a}
                                  onOpen={() =>
                                    setTransformModal({
                                      target: { kind: "layer", name: l.name, label: l.name },
                                      assignment: a,
                                    })
                                  }
                                />
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
                          const blockParts = b.part_ids.map((id) => partById.get(id)).filter((part): part is Part => !!part);
                          return (
                            <div key={b.name} className="rounded-lg border border-cyan-900/50 bg-cyan-950/10 p-3">
                              <div className="flex items-center gap-2">
                                <svg viewBox="0 0 24 24" className="h-4 w-4 text-cyan-400" fill="currentColor"><path d="M12 2 3 7v10l9 5 9-5V7l-9-5Zm0 2.3 6.7 3.7L12 11.7 5.3 8 12 4.3Z" /></svg>
                                <span className="text-sm text-zinc-200">{b.name}</span>
                                <span className="text-[11px] text-zinc-500">×{b.instance_count} instances</span>
                                <span className="ml-auto rounded border border-cyan-700/40 bg-cyan-500/10 px-1.5 py-0.5 text-[10px] text-cyan-300">BlockEdit</span>
                              </div>
                              <div className="mt-2 flex flex-wrap items-center gap-2">
                                {a?.finish ? (
                                  <><img src={a.finish.thumb_url} alt="" className="h-6 w-6 rounded object-cover" />
                                    <span className="text-xs text-zinc-400">{a.finish.name}</span>
                                    <AssignmentTransformButton
                                      assignment={a}
                                      onOpen={() =>
                                        setTransformModal({
                                          target: { kind: "block", name: b.name, label: b.name },
                                          assignment: a,
                                        })
                                      }
                                    />
                                    <button onClick={() => assign({ kind: "block", name: b.name }, null)} className="text-zinc-600 hover:text-red-400">✕</button></>
                                ) : <span className="text-[11px] text-zinc-600">inherits parent / layer finishes</span>}
                                <button onClick={() => setPicker({ kind: "block", name: b.name })}
                                  className="ml-auto rounded-lg border border-zinc-700 px-2 py-1 text-[11px] text-zinc-300 hover:bg-zinc-800">
                                  {a ? "Change" : "Assign whole block"}
                                </button>
                              </div>
                              <ul className="mt-2 space-y-1 border-t border-zinc-800/60 pt-2">
                                {blockParts.slice(0, 20).map((p) => {
                                  const target = partTarget(p);
                                  const pa = assignFor({ kind: "part", name: target });
                                  return (
                                    <li key={p.id} className="flex items-center gap-2 text-xs text-zinc-400">
                                      <button className="truncate hover:text-zinc-200" onClick={() => setSelected(new Set([p.id]))}>{p.name}</button>
                                      <span className="text-[10px] text-zinc-600">{p.layer}</span>
                                      <span className="ml-auto flex items-center gap-1">
                                        {pa?.finish && <img src={pa.finish.thumb_url} alt="" className="h-4 w-4 rounded object-cover" />}
                                        <button onClick={() => setPicker({ kind: "part", name: target, label: p.name })}
                                          className="rounded border border-zinc-800 px-1.5 py-0.5 text-[10px] text-zinc-400 hover:bg-zinc-800">
                                          {pa ? "change" : "override"}
                                        </button>
                                        {pa && <button onClick={() => assign({ kind: "part", name: target }, null)} className="text-zinc-600 hover:text-red-400">✕</button>}
                                      </span>
                                    </li>
                                  );
                                })}
                              </ul>
                              {blockParts.length > 20 && <p className="mt-1 text-[11px] text-zinc-500">Showing 20 of {blockParts.length} parts; use the search below for the rest.</p>}
                            </div>
                          );
                        })}
                      </div>
                    </section>
                  )}
                  <section>
                    <h3 className="mb-2 text-xs uppercase tracking-wide text-zinc-500">All parts · {matchingParts.length}</h3>
                    <input value={partSearch} aria-label="Search parts" placeholder="Search name, layer or block"
                      onChange={(event) => { setPartSearch(event.target.value); setPartLimit(100); }}
                      className="mb-2 w-full rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-xs text-zinc-200 outline-none focus:border-amber-500/60" />
                    <div className="max-h-80 space-y-1 overflow-y-auto">
                      {matchingParts.slice(0, partLimit).map((p) => {
                        const target = partTarget(p);
                        const pa = assignFor({ kind: "part", name: target });
                        const dims = p.bbox.max.map((value, index) => Math.round((value - p.bbox.min[index]) * 100) / 100).join(" × ");
                        return <div key={p.id} className="flex items-center gap-2 rounded border border-zinc-800 bg-zinc-900/50 px-2 py-1.5">
                          <button onClick={() => setSelected(new Set([p.id]))} className="min-w-0 flex-1 text-left">
                            <span className="block truncate text-xs text-zinc-200">{p.name}</span>
                            <span className="block truncate text-[10px] text-zinc-500">{p.layer}{p.block ? ` · ${p.block}` : " · top level"} · {dims} in{p.renderable === false ? " · linework" : ""}</span>
                          </button>
                          <button onClick={() => setPicker({ kind: "part", name: target, label: p.name })}
                            className="rounded border border-zinc-700 px-2 py-1 text-[10px] text-zinc-300 hover:bg-zinc-800">{pa ? "Change" : "Assign"}</button>
                        </div>;
                      })}
                    </div>
                    {partLimit < matchingParts.length && <button onClick={() => setPartLimit((value) => value + 100)}
                      className="mt-2 text-xs text-amber-400 hover:underline">Show more ({Math.min(partLimit, matchingParts.length)} of {matchingParts.length})</button>}
                  </section>
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
                  {model.assignments.map((a) => {
                    const partLabel = a.target_kind === "part" ? (model.structure?.parts.find((p) => partTarget(p) === a.target_name)?.name || `${a.target_name} (stale target)`) : a.target_name;
                    return (
                    <div key={a.id} className="flex items-center gap-3 rounded-lg border border-zinc-800 bg-zinc-900/50 px-3 py-2">
                      <span className={`rounded border px-1.5 py-0.5 text-[10px] uppercase ${a.target_kind === "layer" ? "border-zinc-700 text-zinc-400" : a.target_kind === "block" ? "border-cyan-700/50 text-cyan-300" : "border-amber-700/50 text-amber-300"}`}>
                        {a.target_kind}
                      </span>
                      <span className="min-w-0 flex-1 truncate text-sm text-zinc-200">{partLabel}</span>
                      {a.finish && <img src={a.finish.thumb_url} alt="" className="h-7 w-7 rounded object-cover" />}
                      <span className="w-28 truncate text-xs text-zinc-400">{a.finish?.name}</span>
                      {a.finish && (
                        <AssignmentTransformButton
                          assignment={a}
                          onOpen={() =>
                            setTransformModal({
                              target: { kind: a.target_kind, name: a.target_name, label: partLabel },
                              assignment: a,
                            })
                          }
                        />
                      )}
                      <button onClick={() => setPicker({ kind: a.target_kind, name: a.target_name, label: partLabel })}
                        className="rounded-lg border border-zinc-700 px-2 py-1 text-[11px] text-zinc-300 hover:bg-zinc-800">Change</button>
                      <button onClick={() => assign({ kind: a.target_kind, name: a.target_name }, null)}
                        className="rounded p-1 text-zinc-600 hover:bg-zinc-800 hover:text-red-400">✕</button>
                    </div>
                  );})}
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
                        <span className="text-zinc-300">{r.source} · {r.quality} · {r.camera}</span>
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
        title={picker ? `Assign finish → ${picker.kind}: ${picker.label || (picker.kind === "part" ? model.structure?.parts.find((p) => partTarget(p) === picker.name)?.name : picker.name) || picker.name}` : ""}
        initialScale={picker ? assignFor(picker)?.scale_multiplier || 1 : 1}
        initialFinishId={picker ? assignFor(picker)?.finish_id || null : null}
        onPick={(f: Finish, scale: number) => {
          if (!picker) return;
          const prev = assignFor(picker);
          assign(
            picker,
            f.id,
            scale,
            prev?.rotation_deg || 0,
            prev?.offset_u_in || 0,
            prev?.offset_v_in || 0
          );
        }} />
      {transformModal && transformModal.assignment.finish && (
        <FinishSettingsModal
          targetLabel={`${transformModal.target.kind}: ${
            transformModal.target.label || transformModal.target.name
          }`}
          finish={transformModal.assignment.finish}
          initial={{
            scale_multiplier: transformModal.assignment.scale_multiplier || 1,
            rotation_deg: transformModal.assignment.rotation_deg || 0,
            offset_u_in: transformModal.assignment.offset_u_in || 0,
            offset_v_in: transformModal.assignment.offset_v_in || 0,
          }}
          onClose={() => setTransformModal(null)}
          onApply={(next: FinishTransformSettings) => {
            assign(
              transformModal.target,
              transformModal.assignment.finish_id,
              next.scale_multiplier,
              next.rotation_deg,
              next.offset_u_in,
              next.offset_v_in
            );
            setTransformModal(null);
          }}
        />
      )}
      <AutoMatchModal open={autoOpen} onClose={() => setAutoOpen(false)} modelId={modelId} onApplied={refresh} />
      <ApplyPresetModal open={applyOpen} onClose={() => setApplyOpen(false)} modelId={modelId} onApplied={refresh} />
      <Modal open={saveOpen} onClose={() => setSaveOpen(false)} title="Save mapping as preset">
        <label className="mb-1.5 block text-xs uppercase tracking-wide text-zinc-500">Preset name</label>
        <input value={presetName} onChange={(e) => setPresetName(e.target.value)}
          className="w-full rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm text-zinc-200 outline-none focus:border-amber-500/60" />
        <p className="mt-3 text-xs leading-relaxed text-zinc-500">
          Layer and block rules use exact names; individual Rhino parts use exact geometry identities.
          You can edit name rules later to match similar drawings. Review matches when applying a preset.
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
        initialMode={renderMode}
        currentCameraPose={cameraPose}
        savedViews={savedViews}
        namedViews={model.structure?.named_views || []}
        skuLayers={model.structure?.sku_layers || []}
        partLayers={model.structure?.layers || []}
        blocks={model.structure?.blocks || []}
        parts={model.structure?.parts || []}
        targetSchema={model.structure?.target_schema}
        assignments={model.assignments || []}
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
