import { esc } from "./common.js";

const $ = (s) => document.querySelector(s);
const FTS = "https://archive.org/services/search/beta/page_production/";
const SCOPE_LABEL = {
  all: "All historical Indian newspapers and gazettes",
  gazettes: "Gazette of India and state gazettes (877,000+ issues)",
  "bombay-papers": "Bombay papers: Courier, Gazette, Guardian, Chronicle (1811-1958)",
  "calcutta-papers": "Calcutta papers: Calcutta Journal, Hindoo Patriot, Indian Mirror (1819-1891)",
  "vernacular-reports": "Indian-language papers in translation: Vernacular Newspaper Reports (1868-1938)",
  tamil: "Tamil newspapers and periodicals",
  telugu: "Zamin Ryot (Telugu)",
};
let catalog, scopes, page = 1, lastQuery = null;

const fmt = (n) => n.toLocaleString();
const span = (years) => {
  const ys = Object.keys(years).map(Number).filter((y) => y > 1600 && y < 2100);
  return ys.length ? [Math.min(...ys), Math.max(...ys)] : null;
};

function spark(years, w = 220, h = 34, range = null) {
  const s = span(years);
  if (!s) return "";
  const [a, z] = range || s, n = z - a + 1;
  const max = Math.max(...Object.values(years));
  const bw = w / n;
  const bars = Object.entries(years).filter(([y]) => +y >= a && +y <= z).map(([y, c]) => {
    const bh = Math.max(1, Math.sqrt(c / max) * h);  // square root keeps small years visible
    return `<rect x="${((+y - a) * bw).toFixed(2)}" y="${(h - bh).toFixed(2)}" width="${Math.max(1, bw - 0.4).toFixed(2)}" height="${bh.toFixed(2)}"><title>${y}: ${fmt(c)}</title></rect>`;
  }).join("");
  return `<svg class="spark" viewBox="0 0 ${w} ${h}" preserveAspectRatio="none" role="img" aria-label="Issues per year, ${a} to ${z}">${bars}</svg>
    <div class="axis"><span>${a}</span><span>${z}</span></div>`;
}

const iaSearch = (q) => `https://archive.org/search?query=${encodeURIComponent(q)}`;

function sourceCard(s) {
  const sp = span(s.years);
  const badge = s.sampled ? `<span class="badge" title="Public-domain issues are sampled into this archive's full text">Sampled here</span>`
    : s.rights === "full" ? `<span class="badge" title="Public domain; searchable live but not copied into this archive">Search live</span>`
    : `<span class="badge" title="May be in copyright: catalogued and linked only">Link only</span>`;
  return `<div class="card">
    <div class="kicker">${esc(s.language)} · ${esc(s.place)}</div>
    <h3>${esc(s.name)}</h3>
    <p>${esc(s.note)}</p>
    ${spark(s.years)}
    <div class="stats">${fmt(s.total)} items${sp ? `, ${sp[0]}-${sp[1]}` : ""} ${badge}<br>
      <a href="${iaSearch(s.query)}" target="_blank" rel="noopener">Browse at the Internet Archive</a>
      ${s.rights === "full" ? ` · <a href="#search" data-scope-query="${esc(s.query)}" data-scope-name="${esc(s.name)}">Search inside</a>` : ""}</div>
  </div>`;
}

function renderCatalog() {
  const groups = {};
  for (const s of catalog.sources) (groups[s.group] ||= []).push(s);
  const papers = Object.entries(groups).filter(([g]) => g !== "Gazettes");
  $("#papers").innerHTML = papers.map(([g, ss]) => `<h3 class="group">${esc(g)}</h3><div class="grid">${ss.map(sourceCard).join("")}</div>`).join("");

  const gz = catalog.gazettes;
  const dli = catalog.sources.find((s) => s.id === "dli-gazettes");
  const row = (g) => {
    const sp = span(g.years);
    const q = g.query || `collection:gazetteofindia AND title:("${g.name.replace("Gazette of India: ", "")}")`;
    return `<tr><td>${esc(g.name)}</td><td class="num">${fmt(g.total)}</td><td>${sp ? `${sp[0]}-${sp[1]}` : ""}</td>
      <td class="sparkcell">${spark(g.years, 160, 22, axis)}</td>
      <td><a href="${iaSearch(g.query || "collection:gazetteofindia " + g.name)}" target="_blank" rel="noopener">Browse</a> ·
      <a href="#search" data-scope-query="${esc(q)}" data-scope-name="${esc(g.name)}">Search</a></td></tr>`;
  };
  // one shared time axis so rows can be compared at a glance
  const spans = gz.map((g) => span(g.years)).filter(Boolean);
  const axis = [Math.min(...spans.map((x) => x[0])), Math.max(...spans.map((x) => x[1]))];
  const top = gz.slice(0, 25), rest = gz.slice(25);
  $("#gazettes").innerHTML = `
    <p class="sans small muted">${fmt(catalog.gazette_total)} issues in ${gz.length} series in the Internet Archive's
      <a href="https://archive.org/details/gazetteofindia">gazetteofindia</a> collection${dli ? `, plus ${fmt(dli.total)} bound historical volumes from the Digital Library of India` : ""}.</p>
    <div class="table-wrap"><table><thead><tr><th>Series</th><th class="num">Issues</th><th>Years</th><th>Issues per year, ${axis[0]}-${axis[1]}</th><th></th></tr></thead>
    <tbody>${top.map(row).join("")}</tbody></table></div>
    ${rest.length ? `<details style="margin-top:10px"><summary class="sans small">All ${gz.length} series</summary>
      <div class="table-wrap"><table><tbody>${rest.map(row).join("")}</tbody></table></div></details>` : ""}
    ${dli ? `<div class="grid" style="margin-top:18px">${sourceCard(dli)}</div>` : ""}`;

  const tot = catalog.sources.reduce((a, s) => a + s.total, 0) + catalog.gazette_total;
  $("#totals").textContent = `${fmt(tot)} items catalogued`;
}

function setScope(query, name) {
  const sel = $("#s-scope");
  let opt = [...sel.options].find((o) => o.value === query);
  if (!opt) { opt = new Option(name, query); sel.add(opt); }
  sel.value = query;
  $("#s-q").focus();
}

document.addEventListener("click", (e) => {
  const a = e.target.closest("[data-scope-query]");
  if (a) { setScope(a.dataset.scopeQuery, a.dataset.scopeName); }
  const chip = e.target.closest(".chip[data-q]");
  if (chip) { $("#s-q").value = chip.dataset.q; if (chip.dataset.scope) $("#s-scope").value = chip.dataset.scope; run(1); }
});

function scopeQuery(v) { return scopes[v] || v; }

async function run(p) {
  const q = $("#s-q").value.trim();
  if (!q) return;
  page = p;
  const from = $("#s-from").value, to = $("#s-to").value;
  let uq = `(${q}) AND ${scopeQuery($("#s-scope").value)}`;
  if (from || to) uq += ` AND year:[${from || 1700} TO ${to || 2100}]`;
  lastQuery = q;
  const status = $("#s-status");
  status.textContent = "Searching the Internet Archive ...";
  if (p === 1) $("#s-results").innerHTML = "";
  try {
    const url = `${FTS}?${new URLSearchParams({ user_query: uq, hits_per_page: 20, page: p, service_backend: "fts" })}`;
    const r = await fetch(url);
    const d = await r.json();
    const body = d?.response?.body?.hits;
    if (!body) throw new Error(d?.response?.error || "no results");
    status.textContent = `${fmt(body.total)} matching pages. Showing ${Math.min(body.total, p * 20)}.`;
    const html = body.hits.map((h) => {
      const f = h.fields;
      const snip = (h.highlight?.text || []).map((t) => esc(t.replace(/\s+/g, " ")).replace(/\{\{\{(.*?)\}\}\}/g, "<mark>$1</mark>")).join(" … ");
      const link = `https://archive.org/details/${encodeURIComponent(f.identifier)}${f.page_num ? `/page/n${f.page_num}` : ""}?q=${encodeURIComponent(q)}`;
      return `<article class="ev"><div class="meta"><span class="paper">${esc(f.title || f.identifier)}</span>
        <span class="where">${esc((f.date || "").slice(0, 10))}${f.page_num ? ` · page ${f.page_num + 1}` : ""}</span></div>
        <blockquote>${snip || "<i>No preview</i>"}</blockquote>
        <div class="actions"><a href="${link}" target="_blank" rel="noopener">Open at the Internet Archive</a></div></article>`;
    }).join("");
    $("#s-results").insertAdjacentHTML("beforeend", html);
    $("#s-more").hidden = p * 20 >= body.total;
  } catch (err) {
    status.textContent = `The Internet Archive search did not answer (${err.message}). Try again in a moment.`;
  }
}

$("#s-form").addEventListener("submit", (e) => { e.preventDefault(); run(1); });
$("#s-more").addEventListener("click", () => run(page + 1));

(async function init() {
  catalog = await (await fetch("data/india-catalog.json")).json();
  scopes = catalog.scopes;
  const sel = $("#s-scope");
  for (const [k] of Object.entries(scopes)) sel.add(new Option(SCOPE_LABEL[k] || k, k));
  renderCatalog();
  const p = new URLSearchParams(location.search);
  if (p.get("q")) { $("#s-q").value = p.get("q"); run(1); }
})().catch((e) => { $("#totals").textContent = `Could not load the catalog: ${e.message}`; });
