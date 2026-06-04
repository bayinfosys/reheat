import API, { posClass } from "/static/api.js";
import { mountHeader } from "/static/header.js";

(function () {

  const params   = new URLSearchParams(window.location.search);
  const runId    = params.get("run_id");
  const initType = params.get("type") || null;

  if (!runId) {
    document.body.innerHTML =
      "<p style='padding:2rem'>No run_id. " +
      "<a href='/static/index.html'>Back to explorer.</a></p>";
    return;
  }

  document.getElementById("back-link").href =
    `/static/index.html?run_id=${runId}`;

  function clone(id) {
    return document.getElementById(id).content.cloneNode(true).firstElementChild;
  }

  function chip(text, cls = "seed") {
    const el = document.createElement("span");
    el.className = cls;
    el.textContent = text;
    return el;
  }

  // -- nav --

  async function loadNav() {
    const [run, enrichments] = await Promise.all([
      API.runs.show(runId),
      API.enrichments.list(runId),
    ]);

    mountHeader("reheat", `${run.domain} \u00b7 ${runId}`);
    document.title = `reheat -- enrichments -- ${run.domain}`;

    const nav = document.getElementById("enrichment-nav-items");
    nav.innerHTML = "";

    if (!enrichments.length) {
      nav.innerHTML = "<p class='loading'>No enrichments.</p>";
      return;
    }

    enrichments.forEach(e => {
      const item = clone("tpl-nav-item");
      item.dataset.type = e.enrichment_type;
      item.querySelector(".nav-label").textContent = e.enrichment_type;
      item.addEventListener("click", () => selectEnrichment(e, item));
      nav.appendChild(item);
    });

    const first = initType
      ? enrichments.find(e => e.enrichment_type === initType)
      : enrichments[0];

    if (first) {
      const el = nav.querySelector(`[data-type="${first.enrichment_type}"]`);
      selectEnrichment(first, el);
    }
  }

  // -- detail --

  let activeNav = null;

  async function selectEnrichment(meta, navItem) {
    if (activeNav) activeNav.classList.remove("active");
    navItem.classList.add("active");
    activeNav = navItem;

    const detail = document.getElementById("enrichment-detail");
    detail.innerHTML = "<p class='loading'>Loading...</p>";

    try {
      const enrichment = await API.enrichments.show(runId, meta.enrichment_type);
      detail.innerHTML = "";

      const header = clone("tpl-detail-header");
      header.querySelector(".detail-title").textContent =
        enrichment.enrichment_type;
      header.querySelector(".detail-derived").textContent =
        enrichment.derived_from.length
          ? `from: ${enrichment.derived_from.join(", ")}`
          : "no dependencies";
      header.querySelector(".detail-created").textContent =
        new Date(enrichment.created_at).toLocaleString();
      detail.appendChild(header);

      const renderer = RENDERERS[enrichment.enrichment_type];
      if (renderer) {
        detail.appendChild(renderer(enrichment.data));
      } else {
        const p = document.createElement("p");
        p.className = "loading";
        p.textContent = "No renderer for this enrichment type.";
        detail.appendChild(p);
      }

    } catch (e) {
      detail.innerHTML = `<p>Failed to load: ${e.message}</p>`;
    }
  }

  // -- renderers --
  // Each renderer receives enrichment.data and returns a DOM element.

  const RENDERERS = {

    serp(data) {
      const queries   = data.queries || {};
      const container = document.createElement("div");
      const keys      = Object.keys(queries);

      if (!keys.length) {
        container.innerHTML = "<p class='loading'>No data.</p>";
        return container;
      }

      const title = document.createElement("p");
      title.className = "section-title";
      title.textContent = `${keys.length} queries enriched`;
      container.appendChild(title);

      keys.forEach(query => {
        const q    = queries[query];
        const item = clone("tpl-serp-item");

        item.querySelector(".serp-query").textContent = query;

        const paaEl = item.querySelector(".serp-paa");
        if (q.paa && q.paa.length) {
          const chips = item.querySelector(".paa-chips");
          q.paa.forEach(p => chips.appendChild(chip(p)));
        } else {
          paaEl.style.display = "none";
        }

        const relEl = item.querySelector(".serp-related");
        if (q.related && q.related.length) {
          const chips = item.querySelector(".related-chips");
          q.related.forEach(r => chips.appendChild(chip(r)));
        } else {
          relEl.style.display = "none";
        }

        container.appendChild(item);
      });

      return container;
    },

    tags(data) {
      const tags      = data.tags || {};
      const container = document.createElement("div");
      const keys      = Object.keys(tags);

      if (!keys.length) {
        container.innerHTML = "<p class='loading'>No tags.</p>";
        return container;
      }

      const counts = {};
      Object.values(tags).forEach(ts =>
        ts.forEach(t => { counts[t] = (counts[t] || 0) + 1; })
      );
      const sorted = Object.entries(counts).sort((a, b) => b[1] - a[1]);

      const cloudTitle = document.createElement("p");
      cloudTitle.className = "section-title";
      cloudTitle.textContent =
        `${sorted.length} unique tags across ${keys.length} queries`;
      container.appendChild(cloudTitle);

      const cloud = document.createElement("div");
      cloud.className = "tag-cloud";
      sorted.forEach(([tag, count]) =>
        cloud.appendChild(chip(`${tag} (${count})`, "tag-chip"))
      );
      container.appendChild(cloud);

      const tableTitle = document.createElement("p");
      tableTitle.className = "section-title";
      tableTitle.textContent = "Per query";
      container.appendChild(tableTitle);

      const table = document.createElement("table");
      table.className = "data-table";
      table.innerHTML =
        "<thead><tr><th>Query</th><th>Tags</th></tr></thead>";
      const tbody = document.createElement("tbody");

      keys.forEach(query => {
        const row = clone("tpl-tag-row");
        row.querySelector(".col-query").textContent = query;
        const tagCell = row.querySelector(".col-tags");
        (tags[query] || []).forEach(t =>
          tagCell.appendChild(chip(t, "tag-chip"))
        );
        tbody.appendChild(row);
      });

      table.appendChild(tbody);
      container.appendChild(table);
      return container;
    },

    embeddings(data) {
      const embeddings = data.embeddings || [];
      const adjacent   = data.adjacent_embeddings || [];
      const container  = document.createElement("div");

      const title = document.createElement("p");
      title.className = "section-title";
      title.textContent =
        `${embeddings.length} seed embeddings \u00b7 ` +
        `${adjacent.length} adjacent embeddings`;
      container.appendChild(title);

      const note = document.createElement("p");
      note.className = "loading";
      note.style.marginTop = "0.5rem";
      note.textContent =
        "Raw vectors are not displayed. " +
        "See the Intent Map in the report to explore embedding geometry.";
      container.appendChild(note);

      if (!embeddings.length) return container;

      const tableTitle = document.createElement("p");
      tableTitle.className = "section-title";
      tableTitle.style.marginTop = "1rem";
      tableTitle.textContent = "Embedded queries";
      container.appendChild(tableTitle);

      const table = document.createElement("table");
      table.className = "data-table";
      table.innerHTML =
        "<thead><tr><th>Query</th><th>Type</th><th>Length</th></tr></thead>";
      const tbody = document.createElement("tbody");

      embeddings.forEach(e => {
        const row = clone("tpl-embedding-row");
        row.querySelector(".col-query").textContent  = e.query;
        row.querySelector(".col-type").textContent   = e.type || "seed";
        row.querySelector(".col-length").textContent = e.length || "--";
        tbody.appendChild(row);
      });

      table.appendChild(tbody);
      container.appendChild(table);
      return container;
    },

    clusters(data) {
      const assignments = data.assignments || [];
      const container   = document.createElement("div");

      const title = document.createElement("p");
      title.className = "section-title";
      title.textContent =
        `${data.k} clusters \u00b7 ${assignments.length} queries assigned`;
      container.appendChild(title);

      const groups = {};
      assignments.forEach(a => {
        groups[a.cluster_id] = groups[a.cluster_id] || [];
        groups[a.cluster_id].push(a);
      });

      Object.entries(groups)
        .sort((a, b) => parseInt(a[0]) - parseInt(b[0]))
        .forEach(([cid, members]) => {
          const block = clone("tpl-cluster-block");
          block.querySelector(".cluster-id").textContent = `Cluster ${cid}`;
          block.querySelector(".cluster-count").textContent =
            `${members.length} queries`;

          const queriesEl = block.querySelector(".cluster-block__queries");
          members
            .sort((a, b) => a.distance_to_centroid - b.distance_to_centroid)
            .forEach(m => {
              const line = clone("tpl-cluster-query");
              line.textContent =
                `${m.query} \u00b7 d=${m.distance_to_centroid.toFixed(3)}`;
              queriesEl.appendChild(line);
            });

          container.appendChild(block);
        });

      return container;
    },

    gap(data) {
      const gaps        = data.gaps_per_seed || {};
      const overlapping = data.overlapping_gaps || [];
      const container   = document.createElement("div");

      if (overlapping.length) {
        const title = document.createElement("p");
        title.className = "section-title";
        title.textContent = `${overlapping.length} overlapping gaps`;
        container.appendChild(title);

        overlapping.slice(0, 20).forEach(o => {
          const item = clone("tpl-gap-item");
          item.querySelector(".gap-seed").textContent = o.query;
          const chips = item.querySelector(".gap-chips");
          (o.seeds || []).slice(0, 5).forEach(s => chips.appendChild(chip(s)));
          container.appendChild(item);
        });
      }

      const title2 = document.createElement("p");
      title2.className = "section-title";
      title2.textContent =
        `${Object.keys(gaps).length} seeds with gaps`;
      container.appendChild(title2);

      Object.entries(gaps).slice(0, 30).forEach(([query, adjacents]) => {
        const item = clone("tpl-gap-item");
        item.querySelector(".gap-seed").textContent = query;
        const chips = item.querySelector(".gap-chips");
        (adjacents || []).slice(0, 6).forEach(a => chips.appendChild(chip(a)));
        container.appendChild(item);
      });

      return container;
    },

    opportunities(data) {
      const opps      = data.opportunities || [];
      const container = document.createElement("div");

      const title = document.createElement("p");
      title.className = "section-title";
      title.textContent = `${opps.length} opportunities`;
      container.appendChild(title);

      opps.slice(0, 100).forEach(o => {
        const item = clone("tpl-opp-item");
        item.querySelector(".opp-query").textContent = o.query;
        item.querySelector(".opp-score").textContent = `score ${o.score}`;
        item.querySelector(".opp-rec").textContent   = o.recommendation;
        container.appendChild(item);
      });

      return container;
    },

    summaries(data) {
      const summaries = data.summaries || [];
      const container = document.createElement("div");

      const title = document.createElement("p");
      title.className = "section-title";
      title.textContent = `${summaries.length} cluster summaries`;
      container.appendChild(title);

      summaries
        .sort((a, b) => b.total_impressions - a.total_impressions)
        .forEach(s => {
          const block = clone("tpl-summary-block");
          block.querySelector(".summary-block__label").textContent =
            s.label || `Cluster ${s.cluster_id}`;
          block.querySelector(".summary-block__description").textContent =
            s.description || "";
          block.querySelector(".summary-block__meta").textContent =
            `${s.query_count} queries \u00b7 ` +
            `${s.total_impressions} impressions \u00b7 ` +
            `avg position ${s.avg_position ? s.avg_position.toFixed(1) : "--"}`;
          const chips = block.querySelector(".summary-block__chips");
          (s.top_queries || []).forEach(q => chips.appendChild(chip(q)));
          container.appendChild(block);
        });

      return container;
    },

  };

  loadNav().catch(e => {
    document.getElementById("enrichment-nav-items").innerHTML =
      `<p class='loading'>Failed: ${e.message}</p>`;
  });

})();
