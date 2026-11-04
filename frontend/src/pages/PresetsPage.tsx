import { useEffect, useState } from "react";
import { api, toast } from "../api";
import { usePoll } from "../hooks";
import Modal from "../components/Modal";
import type { Finish, Preset, PresetRule } from "../types";

const blankRule = (): PresetRule => ({ match: "contains", pattern: "", finish_id: 0, target_kind: "layer" });

export default function PresetsPage() {
  const { data, refresh } = usePoll<Preset[]>(() => api.get("/api/presets"), 15000);
  const finishes = usePoll<Finish[]>(() => api.get("/api/finishes"), 60000);
  const [editing, setEditing] = useState<Preset | "new" | null>(null);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [rules, setRules] = useState<PresetRule[]>([]);

  const open = (p: Preset | "new") => {
    setEditing(p);
    if (p === "new") { setName(""); setDescription(""); setRules([blankRule()]); }
    else { setName(p.name); setDescription(p.description); setRules(p.rules.map((r) => ({ ...r }))); }
  };

  const save = async () => {
    const clean = rules.filter((r) => r.pattern && r.finish_id);
    try {
      if (editing === "new") await api.post("/api/presets", { name, description, rules: clean });
      else if (editing) await api.patch(`/api/presets/${editing.id}`, { name, description, rules: clean });
      toast("Preset saved");
      setEditing(null);
      refresh();
    } catch (e) { toast(e instanceof Error ? e.message : "failed", "err"); }
  };

  const remove = async (p: Preset) => {
    if (!window.confirm(`Delete preset "${p.name}"?`)) return;
    await api.del(`/api/presets/${p.id}`);
    refresh();
  };

  useEffect(() => {
    if (rules.some((r) => r.finish_id === 0) && finishes.data?.length) {
      setRules((rs) => rs.map((r) => (r.finish_id === 0 ? { ...r, finish_id: finishes.data![0].id } : r)));
    }
  }, [finishes.data]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="mx-auto max-w-5xl px-8 py-8">
      <header className="mb-6 flex items-end justify-between">
        <div>
          <h1 className="text-xl font-semibold text-zinc-100">Mapping presets</h1>
          <p className="mt-1 text-sm text-zinc-500">Reusable rules: layer/block name pattern → finish. Apply to any model in one click.</p>
        </div>
        <button onClick={() => open("new")} className="rounded-lg bg-amber-500 px-4 py-2 text-sm font-medium text-zinc-950 hover:bg-amber-400">
          New preset
        </button>
      </header>

      <div className="space-y-4">
        {(data || []).map((p) => (
          <div key={p.id} className="rounded-xl border border-zinc-800 bg-zinc-900/50 p-4">
            <div className="flex items-center gap-3">
              <div className="min-w-0 flex-1">
                <div className="text-sm font-medium text-zinc-200">{p.name}</div>
                {p.description && <div className="mt-0.5 text-xs text-zinc-500">{p.description}</div>}
              </div>
              <button onClick={() => open(p)} className="rounded-lg border border-zinc-700 px-3 py-1.5 text-xs text-zinc-300 hover:bg-zinc-800">Edit</button>
              <button onClick={() => remove(p)} className="rounded-lg border border-zinc-800 px-3 py-1.5 text-xs text-zinc-500 hover:border-red-900 hover:text-red-400">Delete</button>
            </div>
            <div className="mt-3 flex flex-wrap gap-2">
              {p.rules.map((r, i) => (
                <span key={i} className="flex items-center gap-1.5 rounded-lg border border-zinc-800 bg-zinc-950 px-2 py-1 text-[11px] text-zinc-400">
                  <span className="text-zinc-600">{r.match}</span>
                  <code className="text-amber-300">{r.pattern}</code>
                  <svg viewBox="0 0 24 24" className="h-3 w-3 text-zinc-600" fill="none" stroke="currentColor" strokeWidth="2"><path d="M5 12h14m-6-6 6 6-6 6" /></svg>
                  {r.finish_thumb && <img src={r.finish_thumb} alt="" className="h-4 w-4 rounded object-cover" />}
                  <span className="text-zinc-300">{r.finish_name}</span>
                </span>
              ))}
            </div>
          </div>
        ))}
        {(data || []).length === 0 && (
          <div className="rounded-xl border border-dashed border-zinc-800 py-20 text-center text-sm text-zinc-500">
            No presets yet. Map a model, then “Save preset” from the workspace.
          </div>
        )}
      </div>

      <Modal open={!!editing} onClose={() => setEditing(null)} title={editing === "new" ? "New preset" : "Edit preset"} wide>
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="mb-1 block text-xs uppercase tracking-wide text-zinc-500">Name</label>
              <input value={name} onChange={(e) => setName(e.target.value)}
                className="w-full rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm text-zinc-200 outline-none focus:border-amber-500/60" />
            </div>
            <div>
              <label className="mb-1 block text-xs uppercase tracking-wide text-zinc-500">Description</label>
              <input value={description} onChange={(e) => setDescription(e.target.value)}
                className="w-full rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm text-zinc-200 outline-none focus:border-amber-500/60" />
            </div>
          </div>
          <div>
            <div className="mb-2 flex items-center justify-between">
              <label className="text-xs uppercase tracking-wide text-zinc-500">Rules</label>
              <button onClick={() => setRules([...rules, blankRule()])} className="text-xs text-amber-400 hover:underline">+ add rule</button>
            </div>
            <div className="space-y-2">
              {rules.map((r, i) => (
                <div key={i} className="flex items-center gap-2">
                  <select value={r.match} onChange={(e) => setRules(rules.map((x, j) => (j === i ? { ...x, match: e.target.value as PresetRule["match"] } : x)))}
                    className="rounded-lg border border-zinc-700 bg-zinc-950 px-2 py-1.5 text-xs text-zinc-300 outline-none">
                    <option value="contains">contains</option>
                    <option value="starts_with">starts with</option>
                    <option value="exact">exact</option>
                    <option value="regex">regex</option>
                  </select>
                  <select value={r.target_kind} onChange={(e) => setRules(rules.map((x, j) => (j === i ? { ...x, target_kind: e.target.value as PresetRule["target_kind"] } : x)))}
                    className="rounded-lg border border-zinc-700 bg-zinc-950 px-2 py-1.5 text-xs text-zinc-300 outline-none">
                    <option value="layer">layer</option>
                    <option value="block">block</option>
                  </select>
                  <input value={r.pattern} placeholder="PATTERN"
                    onChange={(e) => setRules(rules.map((x, j) => (j === i ? { ...x, pattern: e.target.value } : x)))}
                    className="w-36 rounded-lg border border-zinc-700 bg-zinc-950 px-2 py-1.5 font-mono text-xs text-amber-300 outline-none focus:border-amber-500/60" />
                  <svg viewBox="0 0 24 24" className="h-3.5 w-3.5 shrink-0 text-zinc-600" fill="none" stroke="currentColor" strokeWidth="2"><path d="M5 12h14m-6-6 6 6-6 6" /></svg>
                  <select value={r.finish_id} onChange={(e) => setRules(rules.map((x, j) => (j === i ? { ...x, finish_id: Number(e.target.value) } : x)))}
                    className="min-w-0 flex-1 rounded-lg border border-zinc-700 bg-zinc-950 px-2 py-1.5 text-xs text-zinc-300 outline-none">
                    {(finishes.data || []).map((f) => <option key={f.id} value={f.id}>{f.name}</option>)}
                  </select>
                  <button onClick={() => setRules(rules.filter((_, j) => j !== i))} className="p-1 text-zinc-600 hover:text-red-400">✕</button>
                </div>
              ))}
            </div>
          </div>
          <div className="flex justify-end gap-2">
            <button onClick={() => setEditing(null)} className="rounded-lg border border-zinc-700 px-4 py-2 text-sm text-zinc-300 hover:bg-zinc-800">Cancel</button>
            <button onClick={save} disabled={!name.trim()}
              className="rounded-lg bg-amber-500 px-4 py-2 text-sm font-medium text-zinc-950 hover:bg-amber-400 disabled:opacity-40">Save preset</button>
          </div>
        </div>
      </Modal>
    </div>
  );
}
