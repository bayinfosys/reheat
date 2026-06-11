export function posClass(position) {
  if (position <= 10) return "pos-good";
  if (position <= 30) return "pos-ok";
  return "pos-poor";
}

const API = {

  async _get(path) {
    const r = await fetch(path);
    if (!r.ok) throw new Error(`${r.status} ${path}`);
    return r.json();
  },

  async _post(path, body = {}) {
    const r = await fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!r.ok) throw new Error(`${r.status} ${path}`);
    return r.json();
  },

  async _delete(path) {
    const r = await fetch(path, { method: "DELETE" });
    if (!r.ok) throw new Error(`${r.status} ${path}`);
    return r.json();
  },

  runs: {
    list:   (limit = 10) => API._get(`/runs?limit=${limit}`),
    show:   (run_id)     => API._get(`/runs/${run_id}`),
    create: (body)       => API._post("/runs", body),
    delete: (run_id)     => API._delete(`/runs/${run_id}`),
  },

  sources: {
    list:   ()            => API._get("/sources"),
    show:   (source_id)   => API._get(`/sources/${source_id}`),
    create: (body)        => API._post("/sources", body),
    delete: (source_id)   => API._delete(`/sources/${source_id}`),
  },

  enrichments: {
    list:   (run_id)                           => API._get(`/enrichments/${run_id}`),
    show:   (run_id, enrichment_type, source_id = "default") =>
              API._get(`/enrichments/${run_id}/${enrichment_type}/${source_id}`),
    delete: (run_id, enrichment_type, source_id = "default") =>
              API._delete(`/enrichments/${run_id}/${enrichment_type}/${source_id}`),
  },

  enrich: {
    adjacent: (run_id)    => API._post("/enrich/adjacent", { run_id }),
    tags:     (run_id)    => API._post("/enrich/tags",     { run_id }),
    embed:    (run_id)    => API._post("/enrich/embed",    { run_id }),
    cluster:  (run_id, k) => API._post("/enrich/cluster",  { run_id, k }),
  },

  analyse: {
    opportunities: (run_id) => API._post("/analyse/opportunities", { run_id }),
    summarise:     (run_id) => API._post("/analyse/summarise",     { run_id }),
    schedule:      (run_id) => API._post("/analyse/schedule",      { run_id }),
    overview:      (run_id) => API._post("/analyse/overview",      { run_id }),
  },

  project: {
    create: (run_id, method) => API._post("/project",              { run_id, method }),
    read:   (run_id, method) => API._get(`/project/${run_id}/${method}`),
  },

  report: {
    scatter:       { read: (run_id) => API._get(`/report/scatter/${run_id}`)       },
    summary:       { read: (run_id) => API._get(`/report/summary/${run_id}`)       },
    coverage:      { read: (run_id) => API._get(`/report/coverage/${run_id}`)      },
    opportunities: { read: (run_id) => API._get(`/report/opportunities/${run_id}`) },
    overlaps:      { read: (run_id) => API._get(`/report/overlaps/${run_id}`)      },
    schedule:      { read: (run_id) => API._get(`/report/schedule/${run_id}`)      },
    overview:      { read: (run_id) => API._get(`/report/overview/${run_id}`)      },
  },

};

export default API;
