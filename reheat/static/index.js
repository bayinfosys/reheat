import API           from "/static/api.js";
import { render }    from "/static/binder.js";
import { loadTable } from "/static/table.js";

(function () {

  // ---------------------------------------------------------------------------
  // State
  // ---------------------------------------------------------------------------

  const params = new URLSearchParams(window.location.search);
  let runId    = params.get("run_id");
  const loaded = new Set();

  // ---------------------------------------------------------------------------
  // Initialisation
  // ---------------------------------------------------------------------------

  function init() {
    API.runs.list(20)
      .then(function (runs) {
        if (!runs.length) return;
        if (!runId) runId = runs[0].run_id;
        populateRunSelector(runs);
        loadRunMeta(runId);
        loadTab("tab-overview");
      })
      .catch(function (e) { console.error("runs list failed", e); });

    wireTabClicks();
  }

  // ---------------------------------------------------------------------------
  // Run selector
  // ---------------------------------------------------------------------------

  function populateRunSelector(runs) {
    const selector = document.getElementById("run-selector");

    runs.forEach(function (run) {
      const opt  = document.createElement("option");
      opt.value  = run.run_id;
      const date = new Date(run.fetched_at).toLocaleDateString("en-GB", {
        day: "2-digit", month: "short", year: "numeric",
        hour: "2-digit", minute: "2-digit",
      });
      opt.textContent    = run.domain + " -- " + date;
      opt.selected       = run.run_id === runId;
      selector.appendChild(opt);
    });

    selector.addEventListener("change", function () {
      const url = new URL(window.location.href);
      url.searchParams.set("run_id", selector.value);
      window.location.href = url.toString();
    });
  }

  // ---------------------------------------------------------------------------
  // Run meta (header stats)
  // ---------------------------------------------------------------------------

  function loadRunMeta(id) {
    API.runs.show(id)
      .then(function (run) {
        const impressions = run.queries.reduce(function (s, q) { return s + q.impressions; }, 0);
        const clicks      = run.queries.reduce(function (s, q) { return s + q.clicks; },      0);
        document.getElementById("meta-queries").textContent     = run.query_count.toLocaleString();
        document.getElementById("meta-impressions").textContent = impressions.toLocaleString();
        document.getElementById("meta-clicks").textContent      = clicks.toLocaleString();
      })
      .catch(function (e) { console.error("run meta failed", e); });
  }

  // ---------------------------------------------------------------------------
  // Tabs
  // ---------------------------------------------------------------------------

  function wireTabClicks() {
    document.querySelectorAll(".tab").forEach(function (tab) {
      tab.addEventListener("click", function () {
        document.querySelectorAll(".tab").forEach(function (t) { t.classList.remove("active"); });
        document.querySelectorAll(".tab-panel").forEach(function (p) { p.classList.remove("active"); });
        tab.classList.add("active");
        const target = tab.dataset.target;
        document.getElementById(target).classList.add("active");
        loadTab(target);
      });
    });
  }

  function loadTab(target) {
    if (loaded.has(target)) return;
    loaded.add(target);
    const loaders = {
      "tab-overview":      loadOverview,
      "tab-schedule":      loadSchedule,
      "tab-map":           loadScatter,
      "tab-opportunities": loadOpportunities,
      "tab-overlaps":      loadOverlaps,
      "tab-coverage":      loadCoverage,
    };
    if (loaders[target]) loaders[target]();
  }

  // ---------------------------------------------------------------------------
  // Overview
  // ---------------------------------------------------------------------------

  function summarySection(key, title, hint, emptyText, toItem) {
    return { key: key, title: title, hint: hint, emptyText: emptyText, toItem: toItem };
  }

  function buildSummarySections() {
    return [
      summarySection(
        "top_performing",
        "Top Performing Content",
        "Your queries generating the most clicks.",
        "No clicks yet.",
        function (q) {
          return {
            title:  q.query,
            meta:   q.clicks + " clicks \u00b7 " + q.impressions + " impressions \u00b7 position " +
                    q.position.toFixed(1) + " \u00b7 CTR " + (q.ctr * 100).toFixed(1) + "%",
            detail: "",
          };
        }
      ),
      summarySection(
        "top_clusters",
        "Top Query Areas",
        "Your highest-impression topic clusters.",
        "No clusters.",
        function (c) {
          return {
            title:  c.label || "Cluster " + c.cluster_id,
            meta:   c.impressions + " impressions \u00b7 " + c.query_count + " queries",
            detail: c.sample.join(", "),
          };
        }
      ),
      summarySection(
        "missed_opportunities",
        "Missed Opportunities",
        "Content you rank for but not well -- adjacent demand suggests stronger coverage.",
        "None found.",
        function (q) {
          return {
            title:  q.query,
            meta:   "position " + q.position.toFixed(1) + " \u00b7 " + q.impressions + " impressions",
            detail: q.adjacent.join(", "),
          };
        }
      ),
      summarySection(
        "new_opportunities",
        "New Opportunities",
        "Adjacent queries with no existing coverage.",
        "Run analyse opportunities first.",
        function (o) {
          return {
            title:  o.query,
            meta:   "score " + o.score,
            detail: o.seeds.slice(0, 3).join(", "),
          };
        }
      ),
    ];
  }

  function loadOverview() {
    const proseEl   = document.getElementById("overview-prose");
    const summaryEl = document.getElementById("overview-summary");

    Promise.all([
      API.report.overview.read(runId).catch(function () { return null; }),
      API.report.summary.read(runId).catch(function () { return null; }),
    ]).then(function (results) {
      const overview = results[0];
      const summary  = results[1];

      if (overview) {
        const paras = overview.paragraphs ||
          [overview.paragraph_1, overview.paragraph_2, overview.paragraph_3].filter(Boolean);
        proseEl.appendChild(render("tpl-overview-prose", { paragraphs: paras }));
      } else {
        proseEl.appendChild(render("tpl-error-no-data", { command: "reheat analyse overview" }));
      }

      if (summary) {
        buildSummarySections().forEach(function (section) {
          const raw   = summary[section.key] || [];
          const items = raw.length
            ? raw.map(section.toItem)
            : [{ title: section.emptyText, meta: "", detail: "" }];
          summaryEl.appendChild(render("tpl-summary-section", {
            title: section.title,
            hint:  section.hint,
            items: items,
          }));
        });
      }
    });
  }

  // ---------------------------------------------------------------------------
  // Schedule
  // ---------------------------------------------------------------------------

  function scheduleGroupTitles() {
    return {
      expand: "Expand Existing Content",
      new:    "New Content",
      other:  "Other",
    };
  }

  function loadSchedule() {
    const content = document.getElementById("schedule-content");

    API.report.schedule.read(runId)
      .then(function (data) {
        const items = data.schedule || [];

        if (!items.length) {
          content.appendChild(render("tpl-error-no-data", { command: "reheat analyse schedule" }));
          return;
        }

        const groups = {};
        items.forEach(function (item) {
          const key = item.opportunity_type || "other";
          if (!groups[key]) groups[key] = [];
          groups[key].push(item);
        });

        const titles = scheduleGroupTitles();
        Object.keys(titles).forEach(function (key) {
          if (!groups[key] || !groups[key].length) return;
          content.appendChild(render("tpl-schedule-group", {
            title: titles[key],
            items: groups[key],
          }));
        });
      })
      .catch(function (e) {
        content.appendChild(render("tpl-error-general", { message: e.message }));
      });
  }

  // ---------------------------------------------------------------------------
  // Tables
  // ---------------------------------------------------------------------------

  function loadOpportunities() {
    loadTable({
      api:     API.report.opportunities.read(runId),
      tableId: "opportunities-table",
      emptyId: "opportunities-empty",
      bodyId:  "opportunities-body",
      command: "reheat analyse opportunities",
      rows: function (data) {
        return (data.opportunities || []).map(function (o) {
          return render("tpl-opportunity-row", Object.assign({}, o, { seeds: o.seeds.slice(0, 3) }));
        });
      },
    });
  }

  function loadOverlaps() {
    loadTable({
      api:     API.report.overlaps.read(runId),
      tableId: "overlaps-table",
      emptyId: "overlaps-empty",
      bodyId:  "overlaps-body",
      command: "reheat analyse opportunities",
      rows: function (data) {
        return (data.overlapping_gaps || []).map(function (o) {
          return render("tpl-overlap-row", Object.assign({}, o, { seeds: o.seeds.slice(0, 3) }));
        });
      },
    });
  }

  function loadCoverage() {
    loadTable({
      api:     API.report.coverage.read(runId),
      tableId: "coverage-table",
      emptyId: "coverage-empty",
      bodyId:  "coverage-body",
      limit:   200,
      command: "reheat report coverage create",
      rows: function (data) {
        return (data.queries || []).map(function (q) {
          return render("tpl-coverage-row", Object.assign({}, q, {
            ctr:      (q.ctr * 100).toFixed(1) + "%",
            position: q.position.toFixed(1),
          }));
        });
      },
    });
  }

  // ---------------------------------------------------------------------------
  // Scatter (Chart.js)
  // ---------------------------------------------------------------------------

  let chart = null;

  function loadScatter() {
    API.report.scatter.read(runId)
      .then(function (data) {
        buildQueryList(data.datasets);
        buildChart(data.datasets);
      })
      .catch(function (e) { console.error("scatter load failed", e); });
  }

  function buildQueryList(datasets) {
    const listEl = document.getElementById("queryList");
    let seedCount = 0;

    datasets.forEach(function (ds, index) {
      if (ds.isAdjacent) return;
      seedCount++;

      const section = document.getElementById("tpl-cluster-section")
        .content.cloneNode(true).firstElementChild;
      section.dataset.index = index;
      section.querySelector(".cluster-colour").style.background = ds.backgroundColor;
      section.querySelector(".cluster-label").textContent       = ds.label;
      section.querySelector(".cluster-count").textContent       = "(" + ds.data.length + ")";

      const queriesEl = section.querySelector(".cluster-queries");
      ds.data.forEach(function (pt) {
        const item         = document.getElementById("tpl-query-list-item")
          .content.cloneNode(true).firstElementChild;
        item.textContent   = pt.query;
        item.dataset.query = pt.query;
        queriesEl.appendChild(item);
      });

      listEl.appendChild(section);
    });

    document.getElementById("meta-clusters").textContent = seedCount;
  }

  function buildChart(datasets) {
    const listEl   = document.getElementById("queryList");
    let activeItem = null;

    function highlightQuery(query) {
      if (activeItem) activeItem.classList.remove("active");
      const item = listEl.querySelector("[data-query=\"" + CSS.escape(query) + "\"]");
      if (!item) return;
      item.classList.add("active");
      activeItem = item;
      const top = item.offsetTop;
      if (top < listEl.scrollTop || top > listEl.scrollTop + listEl.clientHeight) {
        listEl.scrollTo({ top: top - listEl.clientHeight / 2, behavior: "smooth" });
      }
    }

    listEl.addEventListener("click", function (e) {
      const header = e.target.closest(".cluster-header");
      if (header) {
        const index = parseInt(header.closest(".query-list-cluster").dataset.index);
        chart.data.datasets.forEach(function (ds, i) {
          ds.pointRadius = i === index ? 7 : 3;
        });
        chart.update("none");
      }
      const item = e.target.closest(".query-item");
      if (item) highlightQuery(item.dataset.query);
    });

    chart = new Chart(document.getElementById("scatterChart").getContext("2d"), {
      type: "scatter",
      data: { datasets: datasets },
      options: {
        responsive:          true,
        maintainAspectRatio: false,
        onHover: function (event, elements) {
          if (elements.length) {
            highlightQuery(datasets[elements[0].datasetIndex].data[elements[0].index].query);
          }
        },
        plugins: {
          legend:  { display: false },
          tooltip: { callbacks: {
            label: function (ctx) {
              return (ctx.raw.is_adjacent ? "[" + ctx.raw.type + "] " : "") + ctx.raw.query;
            },
          }},
        },
        scales: { x: { display: false }, y: { display: false } },
      },
    });

    document.getElementById("scatterChart").addEventListener("mouseleave", function () {
      chart.data.datasets.forEach(function (ds) {
        ds.pointRadius = ds.isAdjacent ? 3 : 6;
      });
      chart.update("none");
    });
  }

  // ---------------------------------------------------------------------------
  // Start
  // ---------------------------------------------------------------------------

  init();

})();
