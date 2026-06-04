import API, { posClass } from "/static/api.js";
import { mountHeader } from "/static/header.js";

(function () {

  const params   = new URLSearchParams(window.location.search);
  const runId    = params.get("run_id");
  const initSort = params.get("sort") || "impressions";

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

  let allQueries = [];
  let sortCol    = initSort;
  let sortDir    = "desc";

  API.runs.show(runId)
    .then(run => {
      mountHeader("reheat", `${run.domain} \u00b7 ${runId}`);
      document.title = `reheat -- queries -- ${run.domain}`;

      allQueries = run.queries;
      render();

      document.getElementById("queries-empty").style.display = "none";
      document.getElementById("queries-table").style.display = "";
    })
    .catch(e => {
      document.getElementById("queries-empty").textContent =
        `Failed to load: ${e.message}`;
    });

  function render() {
    const sorted = allQueries.slice().sort((a, b) => {
      const av = a[sortCol], bv = b[sortCol];
      if (typeof av === "string") {
        return sortDir === "asc" ? av.localeCompare(bv) : bv.localeCompare(av);
      }
      return sortDir === "asc" ? av - bv : bv - av;
    });

    const tbody = document.getElementById("queries-body");
    tbody.innerHTML = "";

    sorted.forEach(q => {
      const row = clone("tpl-query-row");
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

    document.querySelectorAll(".data-table th").forEach(th => {
      th.classList.remove("sort-asc", "sort-desc");
      if (th.dataset.col === sortCol) {
        th.classList.add(sortDir === "asc" ? "sort-asc" : "sort-desc");
      }
    });
  }

  document.querySelectorAll(".data-table th").forEach(th => {
    th.addEventListener("click", () => {
      if (sortCol === th.dataset.col) {
        sortDir = sortDir === "asc" ? "desc" : "asc";
      } else {
        sortCol = th.dataset.col;
        sortDir = th.dataset.type === "str" ? "asc" : "desc";
      }
      render();
    });
  });

})();
