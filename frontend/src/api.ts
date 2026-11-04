export async function apiFetch(path: string, init?: RequestInit): Promise<any> {
  const res = await fetch(path, init);
  if (!res.ok) {
    let msg = `${res.status} ${res.statusText}`;
    try {
      const d = await res.json();
      if (d && d.detail) msg = typeof d.detail === "string" ? d.detail : JSON.stringify(d.detail);
    } catch {
      /* ignore */
    }
    throw new Error(msg);
  }
  return res.json();
}

export const api = {
  get: (p: string) => apiFetch(p),
  post: (p: string, body?: unknown) =>
    apiFetch(p, {
      method: "POST",
      headers: body !== undefined ? { "Content-Type": "application/json" } : undefined,
      body: body !== undefined ? JSON.stringify(body) : undefined,
    }),
  patch: (p: string, body: unknown) =>
    apiFetch(p, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }),
  del: (p: string) => apiFetch(p, { method: "DELETE" }),
  upload: (p: string, fd: FormData) => apiFetch(p, { method: "POST", body: fd }),
};

export function toast(msg: string, kind: "ok" | "err" = "ok") {
  window.dispatchEvent(new CustomEvent("app-toast", { detail: { msg, kind } }));
}

export function fmtDate(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}
