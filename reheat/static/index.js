import API, { posClass } from "/static/api.js";
import { mountHeader } from "/static/header.js";

const ENRICHMENT_ORDER = [
  "serp", "tags", "embeddings", "clusters",
  "gap", "summaries", "opportunities",
];

function clone(id) {
  return document.getElementById(id).content.cloneNode(true).firstElementChild;
}

function formatDate(iso) {
  return iso ? new Date(iso).toLocaleString() : "unknown";
}

function seedChip(text) {
  const el = document.createElement("span");
  el.className = "seed";
  el.textContent = text;
  return el;
}

// -- run list --

async function loadRuns() {
  const container = document.getElementById("run-list-items");
  try {
    const runs = await API.runs.list(50);
    container.innerHTML = "";

    if (!runs.length) {
      container.innerHTML = "<p class='loading' style='padding:1rem'>No runs found.</p>";
      return;
    }

    runs.forEach(run => {
      const el = clone("tpl-run-item");
      el.querySelector(".run-item__id").textContent = run.run_id;
      el.querySelector(".run-item__meta").textContent =
        `${run.domain} \u00b7 ${run.query_count} queries \u00b7 ${formatDate(run.fetched_at)}`;
      el.addEventListener("click", () => selectRun(run.run_id, el));
      container.appendChild(el);
      loadEnrichmentBadges(run.run_id, el.querySelector(".run-item__badges"));
    });

  } catch (e) {
    container.innerHTML =
      `<p class='loading' style='padding:1rem'>Failed to load: ${e.message}</p>`;
  }
}

async function loadEnrichmentBadges(run_id, container) {
  try {
    const enrichments = await API.enrichments.list(run_id);
    enrichments.forEach(e => {
      const badge = clone("tpl-badge");
      badge.textContent = e.enrichment_type;
      badge.classList.add("badge--done");
      container.appendChild(badge);
    });
  } catch (_) {}
}

// -- run detail --

let activeItem = null;

function linkStat(el, selector, href) {
  const item = el.querySelector(selector).closest(".meta-item");
  item.style.cursor = "pointer";
  item.addEventListener("click", () => { location.href = href; });
}

async function selectRun(run_id, item) {
  if (activeItem) activeItem.classList.remove("active");
  item.classList.add("active");
  activeItem = item;

  const detail = document.getElementById("run-detail");
  detail.innerHTML = "<p class='loading'>Loading...</p>";

  try {
const [run, enrichments] = await Promise.all([
  API.runs.show(run_id),
  API.enrichments.list(run_id),
]);

let hasReport = false;
try {
  await API.report.scatter.read(run_id);
  hasReport = true;
} catch (_) {}

    const enrichmentTypes = new Set(enrichments.map(e => e.enrichment_type));
    const impressions = run.queries.reduce((s, q) => s + q.impressions, 0);
    const clicks = run.queries.reduce((s, q) => s + q.clicks, 0);

    const el = clone("tpl-run-detail");

    // header
    el.querySelector(".run-detail__title").textContent = run.domain;
    el.querySelector(".run-detail__subtitle").textContent = run.run_id;

    // report button
    const actions = el.querySelector(".run-detail__actions");
    if (hasReport) {
      const btn = clone("tpl-btn-report");
      btn.href = `/static/report.html?run_id=${run_id}`;
      actions.appendChild(btn);
    } else {
      actions.appendChild(clone("tpl-btn-no-report"));
    }

    // stats
    linkStat(el, ".stat-queries",     `/static/queries.html?run_id=${run_id}&sort=impressions`);
    linkStat(el, ".stat-impressions", `/static/queries.html?run_id=${run_id}&sort=impressions`);
    linkStat(el, ".stat-clicks",      `/static/queries.html?run_id=${run_id}&sort=clicks`);
    linkStat(el, ".stat-enrichments", `/static/enrichments.html?run_id=${run_id}`);

    // enrichment badges
    const badgeList = el.querySelector(".enrichment-list");
    ENRICHMENT_ORDER.forEach(type => {
      const badge = clone("tpl-badge");
      badge.textContent = type;
      if (enrichmentTypes.has(type)) badge.classList.add("badge--done");
      badgeList.appendChild(badge);
    });

    // query table
    const tbody = el.querySelector("tbody");
    run.queries
      .slice()
      .sort((a, b) => b.impressions - a.impressions)
      .slice(0, 25)
      .forEach(q => {
        const row = clone("tpl-query-row");
        row.querySelector(".col-query").textContent = q.query;
        row.querySelector(".col-impressions").textContent = q.impressions.toLocaleString();
        row.querySelector(".col-clicks").textContent = q.clicks.toLocaleString();
        row.querySelector(".col-ctr").textContent = `${(q.ctr * 100).toFixed(1)}%`;
        const pos = row.querySelector(".col-position");
        pos.textContent = q.position.toFixed(1);
        pos.className = `col-position ${posClass(q.position)}`;
        tbody.appendChild(row);
      });

    detail.innerHTML = "";
    detail.appendChild(el);

  } catch (e) {
    detail.innerHTML = `<p>Failed to load run: ${e.message}</p>`;
  }
}

mountHeader("reheat", "Intent harvesting and market research");
loadRuns();
