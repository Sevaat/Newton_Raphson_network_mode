async function request(url, { method = "GET", body } = {}) {
  const opts = { method };
  if (body !== undefined) {
    if (body instanceof FormData) opts.body = body;
    else { opts.body = JSON.stringify(body); opts.headers = { "Content-Type": "application/json" }; }
  }
  const res = await fetch(url, opts);
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`;
    try { detail = (await res.json()).detail || detail; } catch { /* ignore */ }
    throw new Error(detail);
  }
  return res.status === 204 ? null : res.json();
}

export const api = {
  cases: () => request("/api/cases/"),
  createCase: (name) => request("/api/cases/", { method: "POST", body: { name } }),
  getCase: (id) => request(`/api/cases/${id}/`),
  updateCase: (id, payload) => request(`/api/cases/${id}/`, { method: "PUT", body: payload }),
  deleteCase: (id) => request(`/api/cases/${id}/`, { method: "DELETE" }),
  importCase: (file) => { const fd = new FormData(); fd.append("file", file); return request("/api/cases/import/", { method: "POST", body: fd }); },
  calculate: (id) => request(`/api/cases/${id}/calculate/`, { method: "POST" }),
  getRun: (id) => request(`/api/runs/${id}/`),
};

export async function exportCase(id, name, runId) {
  const res = await fetch(`/api/cases/${id}/export/${runId ? `?run=${runId}` : ""}`);
  if (!res.ok) throw new Error((await res.json()).detail || res.statusText);
  const a = document.createElement("a");
  a.href = URL.createObjectURL(await res.blob());
  a.download = `${name}${runId ? `_result_${runId}` : ""}.json`;
  a.click();
  URL.revokeObjectURL(a.href);
}
