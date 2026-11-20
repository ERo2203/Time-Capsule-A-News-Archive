import { Archive } from "./search.js";

export const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

const MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
export function longDate(iso) {
  if (!iso) return "undated";
  const [y, m, d] = iso.split("-").map(Number);
  return `${MONTHS[m - 1]} ${d}, ${y}`;
}

export const SOURCE_LABEL = {
  loc: "Chronicling America", ia: "Internet Archive", gazette: "Gazette of India",
  headline: "News headline", local: "Local scan",
};

export const hostOf = (url) => { try { return new URL(url).hostname.replace(/^www\./, ""); } catch (_) { return url; } };

/** Chicago-style citation for one page (and, for headlines, the headline itself). */
export function citation(page, chunk) {
  const where = page.place ? ` (${page.place})` : "";
  if (page.src === "headline") {
    const title = chunk ? `"${chunk.text.replace(/[.\s]+$/, "")}." ` : "";
    return `${title}${page.paper}${where}, ${longDate(page.date)}. ${page.url}`;
  }
  const seq = page.seq ? `, image ${page.seq}` : "";
  const repo = page.src === "loc" ? "Library of Congress, Chronicling America"
    : page.src === "ia" || page.src === "gazette" ? "Internet Archive" : "Local scan";
  return `${page.paper}${where}, ${longDate(page.date)}${seq}. ${repo}. ${page.url}`;
}

export function scanCrop(page, bbox, scale = 50) {
  if (!page.iiif || !bbox) return null;
  const r = bbox.map((v) => v.toFixed(2)).join(",");
  return `${page.iiif}/pct:${r}/pct:${scale}/0/default.jpg`;
}

export function qualityMeter(q, src) {
  if (src === "headline") return `<span class="q" title="Born-digital headline: no OCR">born-digital</span>`;
  const cls = q >= 0.85 ? "" : q >= 0.7 ? "mid" : "low";
  const label = q >= 0.85 ? "clean OCR" : q >= 0.7 ? "some OCR noise" : "noisy OCR";
  return `<span class="q ${cls}" title="Heuristic OCR quality ${q.toFixed(2)} (share of letters, word shapes and common words)"><i><b style="width:${Math.round(q * 100)}%"></b></i>${label}</span>`;
}

export async function loadManifest() {
  const r = await fetch("data/manifest.json");
  if (!r.ok) throw new Error("Could not load data/manifest.json");
  return r.json();
}

export async function loadArchive(manifest, onProgress = () => {}) {
  const archive = new Archive();
  let done = 0;
  const shards = await Promise.all(manifest.collections.map(async (c) => {
    const r = await fetch(`data/${c.file}`);
    const json = await r.json();
    onProgress(++done / (manifest.collections.length + 1));
    return [c.id, json];
  }));
  for (const [id, json] of shards) archive.addShard(id, json);
  onProgress(1);
  return archive;
}

// Theme toggle (persists per browser; falls back gracefully when storage is blocked)
(function theme() {
  const root = document.documentElement;
  try { const t = localStorage.getItem("tc-theme"); if (t) root.dataset.theme = t; } catch (_) {}
  document.addEventListener("click", (e) => {
    if (!e.target.closest(".theme-btn")) return;
    const dark = root.dataset.theme ? root.dataset.theme === "dark" : matchMedia("(prefers-color-scheme: dark)").matches;
    root.dataset.theme = dark ? "light" : "dark";
    try { localStorage.setItem("tc-theme", root.dataset.theme); } catch (_) {}
  });
})();
