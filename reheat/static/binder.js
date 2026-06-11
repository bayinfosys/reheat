function clone(templateId) {
  return document.getElementById(templateId).content.cloneNode(true).firstElementChild;
}

function bind(el, data) {
  el.querySelectorAll("[data-field]").forEach(slot => {
    const key   = slot.dataset.field;
    const value = data[key];
    if (value == null) return;

    const itemTpl = slot.querySelector("[data-field-item]");

    if (itemTpl && Array.isArray(value)) {
      slot.removeChild(itemTpl);
      value.forEach(item => {
        const child = itemTpl.cloneNode(true);
        if (typeof item === "string" || typeof item === "number") {
          child.textContent = item;
        } else {
          bind(child, item);
        }
        slot.appendChild(child);
      });
    } else {
      slot.textContent = value;
    }
  });
  return el;
}

export function render(templateId, data) {
  return bind(clone(templateId), data);
}
