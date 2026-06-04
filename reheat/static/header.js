export function mountHeader(title, subtitle) {
  const header = document.querySelector("header");
  if (!header) return;
  header.innerHTML = "";

  const top = document.createElement("div");
  top.className = "header-top";

  const h1 = document.createElement("h1");
  const homeLink = document.createElement("a");
  homeLink.href = "/static/index.html";
  homeLink.textContent = "reheat";
  homeLink.className = "header-home";
  h1.appendChild(homeLink);

  const bayis = document.createElement("a");
  bayis.href = "https://bayis.co.uk";
  bayis.textContent = "Bay Information Systems";
  bayis.className = "header-bayis";
  bayis.target = "_blank";
  bayis.rel = "noopener";

  top.appendChild(h1);
  top.appendChild(bayis);
  header.appendChild(top);

  if (subtitle) {
    const p = document.createElement("p");
    p.textContent = subtitle;
    header.appendChild(p);
  }
}
