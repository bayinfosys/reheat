import API, { posClass } from "/static/api.js";
import { mountHeader } from "/static/header.js";

(function () {

  const params = new URLSearchParams(window.location.search);
  const runId = params.get("run_id");

  mountHeader("reheat", `- \u00b7 ${runId}`);

  if (!runId) {
    document.body.innerHTML =
      "<p style='padding:2rem'>No run_id specified. " +
      "<a href='/static/index.html'>Back to explorer.</a></p>";
    return;
  }

  function clone(id) {
    return document.getElementById(id).content.cloneNode(true).firstElementChild;
  }

  function seedChip(text) {
    const el = document.createElement("span");
    el.className = "seed";
    el.textContent = text;
    return el;
  }

  function recSpan(recommendation) {
    const el = document.createElement("span");
    el.className = `rec-${recommendation.split(" ")[0]}`;
    el.textContent = recommendation;
    return el;
  }

  // -- header --

  API.runs.show(runId)
    .then(run => {
      mountHeader("reheat", `${run.domain} \u00b7 ${runId}`);

      const impressions = run.queries.reduce((s, q) => s + q.impressions, 0);
      const clicks = run.queries.reduce((s, q) => s + q.clicks, 0);

      document.getElementById("meta-queries").textContent =
        run.query_count.toLocaleString();
      document.getElementById("meta-impressions").textContent =
        impressions.toLocaleString();
      document.getElementById("meta-clicks").textContent =
        clicks.toLocaleString();
    })
    .catch(e => console.error("failed to load run header", e));

  // -- tabs --

  const loaded = new Set();

  function loadTab(target) {
    if (loaded.has(target)) return;
    loaded.add(target);
    if (target === "tab-summary")       loadSummary();
    if (target === "tab-map")           loadScatter();
    if (target === "tab-opportunities") loadOpportunities();
    if (target === "tab-overlaps")      loadOverlaps();
    if (target === "tab-coverage")      loadCoverage();
  }

  document.querySelectorAll(".tab").forEach(tab => {
    tab.addEventListener("click", () => {
      document.querySelectorAll(".tab")
        .forEach(t => t.classList.remove("active"));
      document.querySelectorAll(".tab-panel")
        .forEach(p => p.classList.remove("active"));
      tab.classList.add("active");
      const target = tab.dataset.target;
      document.getElementById(target).classList.add("active");
      loadTab(target);
    });
  });

  loadTab("tab-summary");

  // -- summary --

  const SUMMARY_SECTIONS = [
    {
      key:   "top_performing",
      title: "Top Performing Content",
      hint:  "Your queries generating the most clicks.",
      empty: "No clicks yet.",
      render: q => {
        const el = clone("tpl-summary-item");
        el.querySelector(".summary-item__title").textContent = q.query;
        el.querySelector(".summary-item__meta").textContent =
          `${q.clicks} clicks \u00b7 ${q.impressions} impressions \u00b7 ` +
          `position ${q.position.toFixed(1)} \u00b7 CTR ${(q.ctr * 100).toFixed(1)}%`;
        return el;
      },
    },
    {
      key:   "top_clusters",
      title: "Top Query Areas",
      hint:  "Your highest-impression topic clusters.",
      empty: "No clusters.",
      render: c => {
        const el = clone("tpl-summary-item");
        el.querySelector(".summary-item__title").textContent = `Cluster ${c.cluster_id}`;
        el.querySelector(".summary-item__meta").textContent =
          `${c.impressions} impressions \u00b7 ${c.query_count} queries`;
        el.querySelector(".summary-item__detail").textContent =
          c.sample.join(", ");
        return el;
      },
    },
    {
      key:       "missed_opportunities",
      title:     "Missed Opportunities",
      hint:      "Content you rank for but not well -- adjacent demand suggests stronger coverage.",
      empty:     "None found.",
      modifier:  "warning",
      render: q => {
        const el = clone("tpl-summary-item");
        el.classList.add("summary-item--warning");
        el.querySelector(".summary-item__title").textContent = q.query;
        el.querySelector(".summary-item__meta").textContent =
          `position ${q.position.toFixed(1)} \u00b7 ${q.impressions} impressions`;
        const detail = el.querySelector(".summary-item__detail");
        q.adjacent.forEach(a => detail.appendChild(seedChip(a)));
        return el;
      },
    },
    {
      key:      "new_opportunities",
      title:    "New Opportunities",
      hint:     "Adjacent queries with no existing coverage.",
      empty:    "Run analyse opportunities first.",
      modifier: "opportunity",
      render: o => {
        const el = clone("tpl-summary-item");
        el.classList.add("summary-item--opportunity");
        el.querySelector(".summary-item__title").textContent = o.query;
        el.querySelector(".summary-item__meta").textContent = `score ${o.score}`;
        const detail = el.querySelector(".summary-item__detail");
        o.seeds.slice(0, 3).forEach(s => detail.appendChild(seedChip(s)));
        return el;
      },
    },
  ];

  function loadSummary() {
    API.report.summary.read(runId)
      .then(data => {
        const grid = clone("tpl-summary-grid");

        SUMMARY_SECTIONS.forEach(section => {
          const items = data[section.key] || [];
          const sec = clone("tpl-summary-section");
          sec.querySelector(".summary-section__title").textContent = section.title;
          sec.querySelector(".summary-section__hint").textContent = section.hint;
          const container = sec.querySelector(".summary-section__items");

          if (!items.length) {
            const empty = document.createElement("p");
            empty.className = "summary-empty";
            empty.textContent = section.empty;
            container.appendChild(empty);
          } else {
            items.forEach(item => container.appendChild(section.render(item)));
          }

          grid.appendChild(sec);
        });

        const content = document.getElementById("summary-content");
        content.innerHTML = "";
        content.appendChild(grid);
      })
      .catch(e => {
        document.getElementById("summary-content").innerHTML =
          `<p>Failed to load summary: ${e.message}</p>`;
      });
  }

  // -- scatter --

  let chart = null;

  function loadScatter() {
    API.report.scatter.read(runId)
      .then(data => {
        buildQueryList(data.datasets);
        buildChart(data.datasets);
      })
      .catch(e => console.error("scatter load failed", e));
  }

  function buildQueryList(datasets) {
    const listEl = document.getElementById("queryList");
    let seedCount = 0;

    datasets.forEach((ds, index) => {
      if (ds.isAdjacent) return;
      seedCount++;

      const section = clone("tpl-cluster-section");
      section.dataset.index = index;

      const colour = section.querySelector(".cluster-colour");
      colour.style.background = ds.backgroundColor;

      section.querySelector(".cluster-label").textContent = ds.label;
      section.querySelector(".cluster-count").textContent = `(${ds.data.length})`;

      const queriesEl = section.querySelector(".cluster-queries");
      ds.data.forEach(pt => {
        const item = clone("tpl-query-list-item");
        item.textContent = pt.query;
        item.dataset.query = pt.query;
        queriesEl.appendChild(item);
      });

      listEl.appendChild(section);
    });

    document.getElementById("meta-clusters").textContent = seedCount;
  }

  function buildChart(datasets) {
    const listEl = document.getElementById("queryList");
    let activeItem = null;

    function highlightQuery(query) {
      if (activeItem) activeItem.classList.remove("active");
      const item = listEl.querySelector(`[data-query="${CSS.escape(query)}"]`);
      if (!item) return;
      item.classList.add("active");
      activeItem = item;
      const top = item.offsetTop;
      if (top < listEl.scrollTop || top > listEl.scrollTop + listEl.clientHeight) {
        listEl.scrollTo({ top: top - listEl.clientHeight / 2, behavior: "smooth" });
      }
    }

    function resetHighlight() {
      chart.data.datasets.forEach(ds => {
        ds.pointRadius = ds.isAdjacent ? 3 : 6;
      });
      chart.update("none");
    }

    listEl.addEventListener("click", e => {
      const header = e.target.closest(".cluster-header");
      if (header) {
        const index = parseInt(header.closest(".query-list-cluster").dataset.index);
        chart.data.datasets.forEach((ds, i) => {
          ds.pointRadius = i === index ? 7 : 3;
        });
        chart.update("none");
      }
      const item = e.target.closest(".query-item");
      if (item) highlightQuery(item.dataset.query);
    });

    const ctx = document.getElementById("scatterChart").getContext("2d");

    chart = new Chart(ctx, {
      type: "scatter",
      data: { datasets },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        onHover: (event, elements) => {
          if (elements.length > 0) {
            const el = elements[0];
            highlightQuery(datasets[el.datasetIndex].data[el.index].query);
          }
        },
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              label: ctx => {
                const pt = ctx.raw;
                return (pt.is_adjacent ? `[${pt.type}] ` : "") + pt.query;
              },
            },
          },
        },
        scales: { x: { display: false }, y: { display: false } },
      },
    });

    document.getElementById("scatterChart")
      .addEventListener("mouseleave", resetHighlight);
  }

  // -- opportunities --

  function loadOpportunities() {
    API.report.opportunities.read(runId)
      .then(data => {
        const opps = data.opportunities || [];
        const empty = document.getElementById("opportunities-empty");
        const table = document.getElementById("opportunities-table");
        const tbody = document.getElementById("opportunities-body");

        if (!opps.length) {
          empty.textContent = "No opportunities found.";
          return;
        }

        opps.slice(0, 50).forEach(o => {
          const row = clone("tpl-opportunity-row");
          row.querySelector(".col-query").textContent = o.query;
          row.querySelector(".col-score").textContent = o.score.toLocaleString();
          row.querySelector(".col-recommendation").appendChild(recSpan(o.recommendation));
          const seeds = row.querySelector(".col-seeds");
          o.seeds.slice(0, 3).forEach(s => seeds.appendChild(seedChip(s)));
          tbody.appendChild(row);
        });

        empty.style.display = "none";
        table.style.display = "";
      })
      .catch(e => {
        document.getElementById("opportunities-empty").textContent =
          `Failed to load: ${e.message}`;
      });
  }

  // -- overlaps --

  function loadOverlaps() {
    API.report.overlaps.read(runId)
      .then(data => {
        const overlaps = data.overlapping_gaps || [];
        const empty = document.getElementById("overlaps-empty");
        const table = document.getElementById("overlaps-table");
        const tbody = document.getElementById("overlaps-body");

        if (!overlaps.length) {
          empty.textContent = "No overlapping gaps found.";
          return;
        }

        overlaps.slice(0, 30).forEach(o => {
          const row = clone("tpl-overlap-row");
          row.querySelector(".col-query").textContent = o.query;
          row.querySelector(".col-seed-count").textContent = o.seed_count;
          const seeds = row.querySelector(".col-seeds");
          o.seeds.slice(0, 3).forEach(s => seeds.appendChild(seedChip(s)));
          tbody.appendChild(row);
        });

        empty.style.display = "none";
        table.style.display = "";
      })
      .catch(e => {
        document.getElementById("overlaps-empty").textContent =
          `Failed to load: ${e.message}`;
      });
  }

  // -- coverage --

  function loadCoverage() {
    API.report.coverage.read(runId)
      .then(data => {
        const queries = data.queries || [];
        const empty = document.getElementById("coverage-empty");
        const table = document.getElementById("coverage-table");
        const tbody = document.getElementById("coverage-body");

        if (!queries.length) {
          empty.textContent = "No coverage data.";
          return;
        }

        queries.forEach(q => {
          const row = clone("tpl-coverage-row");
          row.querySelector(".col-query").textContent = q.query;
          row.querySelector(".col-impressions").textContent =
            q.impressions.toLocaleString();
          row.querySelector(".col-clicks").textContent =
            q.clicks.toLocaleString();
          row.querySelector(".col-ctr").textContent =
            `${(q.ctr * 100).toFixed(1)}%`;
          const pos = row.querySelector(".col-position");
          pos.textContent = q.position.toFixed(1);
          pos.className = `col-position ${posClass(q.position)}`;
          tbody.appendChild(row);
        });

        empty.style.display = "none";
        table.style.display = "";
      })
      .catch(e => {
        document.getElementById("coverage-empty").textContent =
          `Failed to load: ${e.message}`;
      });
  }

})();
