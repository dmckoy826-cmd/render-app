import { useRef, useState } from "react";
import { api, toast } from "../api";
import { usePoll } from "../hooks";
import Modal from "../components/Modal";
import { CATEGORY_COLOR, CATEGORY_LABEL, type Category, type Finish } from "../types";

const CATS: ("all" | Category)[] = ["all", "laminate", "pet", "product_finish", "other"];

interface FormState {
  name: string;
  category: Category;
  swatch_width_in: number;
  swatch_height_in: number;
  seamless: boolean;
  tags: string;
}

const emptyForm: FormState = { name: "", category: "laminate", swatch_width_in: 24, swatch_height_in: 24, seamless: true, tags: "" };

export default function FinishesPage() {
  const { data, refresh } = usePoll<Finish[]>(() => api.get("/api/finishes"), 15000);
  const [cat, setCat] = useState<"all" | Category>("all");
  const [q, setQ] = useState("");
  const [uploadOpen, setUploadOpen] = useState(false);
  const [edit, setEdit] = useState<Finish | null>(null);
  const [form, setForm] = useState<FormState>(emptyForm);
  const [files, setFiles] = useState<File[]>([]);
  const fileRef = useRef<HTMLInputElement>(null);

  const list = (data || []).filter((f) =>
    (cat === "all" || f.category === cat) &&
    (!q || `${f.name} ${f.tags}`.toLowerCase().includes(q.toLowerCase())));

  const openUpload = () => { setFiles([]); setForm(emptyForm); setUploadOpen(true); };
  const openEdit = (f: Finish) => {
    setEdit(f);
    setForm({ name: f.name, category: f.category, swatch_width_in: f.swatch_width_in, swatch_height_in: f.swatch_height_in, seamless: f.seamless, tags: f.tags });
  };

  const submitUpload = async () => {
    for (const f of files) {
      const fd = new FormData();
      fd.append("file", f);
      fd.append("name", form.name && files.length === 1 ? form.name : "");
      fd.append("category", form.category);
      fd.append("swatch_width_in", String(form.swatch_width_in));
      fd.append("swatch_height_in", String(form.swatch_height_in));
      fd.append("seamless", String(form.seamless));
      fd.append("tags", form.tags);
      try {
        await api.upload("/api/finishes", fd);
      } catch (e) {
        toast(`${f.name}: ${e instanceof Error ? e.message : "failed"}`, "err");
      }
    }
    toast(`Uploaded ${files.length} finish${files.length === 1 ? "" : "es"}`);
    setUploadOpen(false);
    refresh();
  };

  const submitEdit = async () => {
    if (!edit) return;
    try {
      await api.patch(`/api/finishes/${edit.id}`, form);
      toast("Finish updated");
      setEdit(null);
      refresh();
    } catch (e) { toast(e instanceof Error ? e.message : "failed", "err"); }
  };

  const remove = async (f: Finish) => {
    if (!window.confirm(`Delete finish "${f.name}"? Assignments using it will be removed.`)) return;
    await api.del(`/api/finishes/${f.id}`);
    toast("Finish deleted");
    refresh();
  };

  const formFields = (
    <div className="space-y-3">
      <div>
        <label className="mb-1 block text-xs uppercase tracking-wide text-zinc-500">Name</label>
        <input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })}
          placeholder={edit ? edit.name : "Default: file name"}
          className="w-full rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm text-zinc-200 outline-none focus:border-amber-500/60" />
      </div>
      <div>
        <label className="mb-1 block text-xs uppercase tracking-wide text-zinc-500">Category</label>
        <div className="flex gap-2">
          {(Object.keys(CATEGORY_LABEL) as Category[]).map((c) => (
            <button key={c} onClick={() => setForm({ ...form, category: c })}
              className={`rounded-full border px-3 py-1 text-xs ${form.category === c ? CATEGORY_COLOR[c] : "border-zinc-700 text-zinc-500 hover:border-zinc-500"}`}>
              {CATEGORY_LABEL[c]}
            </button>
          ))}
        </div>
      </div>
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="mb-1 block text-xs uppercase tracking-wide text-zinc-500">Swatch width (in)</label>
          <input type="number" min={0.5} step={0.5} value={form.swatch_width_in}
            onChange={(e) => setForm({ ...form, swatch_width_in: Number(e.target.value) || 1 })}
            className="w-full rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm text-zinc-200 outline-none focus:border-amber-500/60" />
        </div>
        <div>
          <label className="mb-1 block text-xs uppercase tracking-wide text-zinc-500">Swatch height (in)</label>
          <input type="number" min={0.5} step={0.5} value={form.swatch_height_in}
            onChange={(e) => setForm({ ...form, swatch_height_in: Number(e.target.value) || 1 })}
            className="w-full rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm text-zinc-200 outline-none focus:border-amber-500/60" />
        </div>
      </div>
      <p className="text-[11px] leading-relaxed text-zinc-500">
        The real-world size the image represents — this drives texture scaling in the viewer and in V-Ray
        (e.g. a 48×96&quot; laminate sheet photo, or a 12×12&quot; crop).
      </p>
      <div>
        <label className="mb-1 block text-xs uppercase tracking-wide text-zinc-500">Tags (helps auto-match)</label>
        <input value={form.tags} onChange={(e) => setForm({ ...form, tags: e.target.value })}
          placeholder="walnut, wood, dark grain"
          className="w-full rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm text-zinc-200 outline-none focus:border-amber-500/60" />
      </div>
      <label className="flex items-center gap-2 text-sm text-zinc-300">
        <input type="checkbox" checked={form.seamless} onChange={(e) => setForm({ ...form, seamless: e.target.checked })} />
        Seamless / tileable image
      </label>
    </div>
  );

  return (
    <div className="mx-auto max-w-7xl px-8 py-8">
      <header className="mb-6 flex items-end justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold text-zinc-100">Finish library</h1>
          <p className="mt-1 text-sm text-zinc-500">Laminate, PET and product-finish swatches with real-world scale.</p>
        </div>
        <button onClick={openUpload} className="rounded-lg bg-amber-500 px-4 py-2 text-sm font-medium text-zinc-950 hover:bg-amber-400">
          Upload finishes
        </button>
      </header>

      <div className="mb-5 flex flex-wrap items-center gap-2">
        {CATS.map((c) => (
          <button key={c} onClick={() => setCat(c)}
            className={`rounded-full border px-3 py-1 text-xs ${cat === c ? "border-amber-500/50 bg-amber-500/15 text-amber-300" : "border-zinc-700 text-zinc-400 hover:border-zinc-500 hover:text-zinc-200"}`}>
            {c === "all" ? "All" : CATEGORY_LABEL[c]}
          </button>
        ))}
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search…"
          className="ml-auto w-56 rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-1.5 text-sm text-zinc-200 placeholder-zinc-500 outline-none focus:border-amber-500/60" />
      </div>

      <div className="grid grid-cols-2 gap-4 md:grid-cols-3 xl:grid-cols-5">
        {list.map((f) => (
          <div key={f.id} className="group overflow-hidden rounded-xl border border-zinc-800 bg-zinc-900/50">
            <div className="relative aspect-square">
              <img src={f.image_url} alt={f.name} className="h-full w-full object-cover" />
              <div className="absolute right-2 top-2 flex gap-1 opacity-0 transition-opacity group-hover:opacity-100">
                <button onClick={() => openEdit(f)} className="rounded bg-zinc-950/80 p-1.5 text-zinc-300 hover:text-amber-300" title="Edit">
                  <svg viewBox="0 0 24 24" className="h-3.5 w-3.5" fill="none" stroke="currentColor" strokeWidth="2"><path d="M4 20h4L19 9a2.8 2.8 0 1 0-4-4L4 16v4Z" /></svg>
                </button>
                <button onClick={() => remove(f)} className="rounded bg-zinc-950/80 p-1.5 text-zinc-300 hover:text-red-400" title="Delete">
                  <svg viewBox="0 0 24 24" className="h-3.5 w-3.5" fill="none" stroke="currentColor" strokeWidth="2"><path d="M4 7h16M10 11v6m4-6v6M6 7l1 13h10l1-13M9 7V4h6v3" /></svg>
                </button>
              </div>
            </div>
            <div className="p-3">
              <div className="truncate text-sm text-zinc-200">{f.name}</div>
              <div className="mt-1.5 flex items-center justify-between">
                <span className={`rounded border px-1.5 py-0.5 text-[10px] ${CATEGORY_COLOR[f.category]}`}>{CATEGORY_LABEL[f.category]}</span>
                <span className="text-[10px] text-zinc-500">{f.swatch_width_in}×{f.swatch_height_in}&quot;{f.seamless ? " · tiles" : ""}</span>
              </div>
              {f.tags && <div className="mt-1.5 truncate text-[11px] text-zinc-600">{f.tags}</div>}
            </div>
          </div>
        ))}
      </div>

      {/* upload modal */}
      <Modal open={uploadOpen} onClose={() => setUploadOpen(false)} title="Upload finish images">
        <div className="space-y-4">
          <input ref={fileRef} type="file" multiple hidden accept=".png,.jpg,.jpeg,.webp"
            onChange={(e) => setFiles(Array.from(e.target.files || []))} />
          <button onClick={() => fileRef.current?.click()}
            className="flex w-full flex-col items-center gap-2 rounded-xl border border-dashed border-zinc-700 py-8 text-sm text-zinc-400 hover:border-amber-500/60 hover:text-zinc-200">
            <svg viewBox="0 0 24 24" className="h-6 w-6" fill="none" stroke="currentColor" strokeWidth="1.6"><path d="M12 16V4m0 0 4 4m-4-4-4 4M4 20h16" /></svg>
            {files.length ? `${files.length} file(s): ${files.map((f) => f.name).join(", ")}` : "Choose PNG / JPG swatch images"}
          </button>
          {formFields}
          <div className="flex justify-end gap-2">
            <button onClick={() => setUploadOpen(false)} className="rounded-lg border border-zinc-700 px-4 py-2 text-sm text-zinc-300 hover:bg-zinc-800">Cancel</button>
            <button onClick={submitUpload} disabled={!files.length}
              className="rounded-lg bg-amber-500 px-4 py-2 text-sm font-medium text-zinc-950 hover:bg-amber-400 disabled:opacity-40">Upload</button>
          </div>
        </div>
      </Modal>

      {/* edit modal */}
      <Modal open={!!edit} onClose={() => setEdit(null)} title={`Edit — ${edit?.name ?? ""}`}>
        <div className="space-y-4">
          {formFields}
          <div className="flex justify-end gap-2">
            <button onClick={() => setEdit(null)} className="rounded-lg border border-zinc-700 px-4 py-2 text-sm text-zinc-300 hover:bg-zinc-800">Cancel</button>
            <button onClick={submitEdit} className="rounded-lg bg-amber-500 px-4 py-2 text-sm font-medium text-zinc-950 hover:bg-amber-400">Save</button>
          </div>
        </div>
      </Modal>
    </div>
  );
}
