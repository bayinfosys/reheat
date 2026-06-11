import { render } from "/static/binder.js";

export function loadTable({ api, tableId, emptyId, bodyId, limit = 50, command = "", rows }) {
  const empty = document.getElementById(emptyId);
  const table = document.getElementById(tableId);
  const tbody = document.getElementById(bodyId);

  api.then(data => {
    const items = rows(data);
    if (!items.length) {
      empty.innerHTML = "";
      empty.appendChild(render("tpl-error-no-data", { command }));
      return;
    }
    items.slice(0, limit).forEach(item => tbody.appendChild(item));
    empty.style.display = "none";
    table.style.display = "";
  }).catch(e => {
    empty.innerHTML = "";
    empty.appendChild(render("tpl-error-general", { message: e.message }));
  });
}
