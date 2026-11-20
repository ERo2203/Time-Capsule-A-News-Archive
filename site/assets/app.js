import { bestSentence, fold, stem } from "./search.js";
import { citation, esc, hostOf, loadArchive, loadManifest, longDate, qualityMeter, scanCrop, SOURCE_LABEL } from "./common.js";

const $ = (s) => document.querySelector(s);
const form = $("#ask-form"), input = $("#q"), status = $("#status"), results = $("#results");
let manifest, archive, colById = {};
let order = "relevance";
let last = null;

function setStatus(html) { status.innerHTML = html; }

async function init() {
  manifest = await loadManifest();
  colById = Object.fromEntries(manifest.collections.map((c) => [c.id, c]));
  const sel = $("#f-col");
  const groups = {};
  for (const c of manifest.collections) (groups[c.group || "Historical events"] ||= []).push(c);
  for (const [g, cs] of Object.entries(groups)) {
    const og = document.createElement("optgroup");
    og.label = g;
    for (const c of cs) og.append(new Option(`${c.title} (${c.stats.dates[0].slice(0, 4)})`, c.id));
    sel.append(og);
  }
  renderExamples();
  const t = manifest.totals;
  $("#totals").textContent = `${t.passages.toLocaleString()} passages from ${t.scanned.toLocaleString()} scanned pages and issues of ${t.scanned_titles} titles`
    + (t.headlines ? `, plus ${t.headlines.toLocaleString()} headlines from ${t.outlets} Indian outlets` : "");

  const bar = $("#loader b");
  setStatus("Loading the archive into your browser ...");
  archive = await loadArchive(manifest, (f) => { bar.style.width = `${Math.round(f * 100)}%`; });
  $("#loader").hidden = true;
  $("#ask-btn").disabled = false;
  setStatus(`Ready. Searching ${archive.chunks.length.toLocaleString()} passages, entirely in your browser.`);

  const p = new URLSearchParams(location.search);
  if (p.get("c")) sel.value = p.get("c");
  if (p.get("from")) $("#f-from").value = p.get("from");
  if (p.get("to")) $("#f-to").value = p.get("to");
  if (p.get("src")) $("#f-src").value = p.get("src");
  if (p.get("q")) { input.value = p.get("q"); run(); }
}

function renderExamples() {
  const box = $("#examples");
  const first = (cs) => cs.flatMap((c) => (c.questions || []).slice(0, 1).map((q) => [q, c.id]));
  const india = manifest.collections.filter((c) => c.group === "India desk");
  const hist = manifest.collections.filter((c) => c.group !== "India desk");
  const picks = [...first(hist).slice(0, 6), ...first(india)];
  box.innerHTML = picks.map(([q, c]) => `<button type="button" class="chip" data-q="${esc(q)}" data-c="${c}">${esc(q)}</button>`).join("");
}

document.addEventListener("click", (e) => {
  const chip = e.target.closest(".chip[data-q]");
  if (chip) {
    input.value = chip.dataset.q;
    if (chip.dataset.c) $("#f-col").value = chip.dataset.c;
    run();
  }
});

form.addEventListener("submit", (e) => { e.preventDefault(); run(); });

function currentFilters() {
  const col = $("#f-col").value, from = $("#f-from").value, to = $("#f-to").value, src = $("#f-src").value;
  return { col, from, to, src };
}

function run() {
  if (!archive) return;
  const q = input.value.trim();
  if (!q) return;
  const f = currentFilters();
  const params = new URLSearchParams({ q });
  if (f.col) params.set("c", f.col);
  if (f.from) params.set("from", f.from);
  if (f.to) params.set("to", f.to);
  if (f.src) params.set("src", f.src);
  history.replaceState(null, "", `?${params}`);

  const filter = (c) => (!f.col || c.page.collection === f.col) && (!f.from || c.page.date >= f.from)
    && (!f.to || c.page.date <= f.to) && (!f.src || c.page.src === f.src);
  const t0 = performance.now();
  const res = archive.search(q, { k: 10, filter });
  const ms = Math.round(performance.now() - t0);
  const weights = new Map(res.qterms.map((t) => [t.term, t.weight * archive.idf(t.term)]));
  const evidence = res.hits.map((h, i) => ({
    n: i + 1, chunk: h.chunk,
    quote: h.chunk.page.src === "headline" ? h.chunk.text : bestSentence(h.chunk.text, weights),
  }));
  last = { q, f, res, evidence, weights };
  setStatus(`${res.total.toLocaleString()} matching passages in ${ms} ms. Showing the ${evidence.length} strongest, at most two per page and four per newspaper.`);
  render();
}

function highlight(text, terms) {
  return esc(text).replace(/[A-Za-z0-9ſ\u00c0-\u024f\u0900-\u0963\u0966-\u0d7f\u0621-\u064a\u0660-\u0669\u0679-\u06d3]+/g, (w) => (terms.has(stem(fold(w))) ? `<mark>${w}</mark>` : w));
}

function timelineSVG(chunks) {
  const dates = chunks.map((c) => c.page.date).filter(Boolean).sort();
  if (dates.length < 2 || dates[0] === dates[dates.length - 1]) return "";
  const toDay = (d) => Date.UTC(+d.slice(0, 4), +d.slice(5, 7) - 1, +d.slice(8, 10)) / 864e5;
  const a = toDay(dates[0]), z = toDay(dates[dates.length - 1]);
  const byYear = z - a > 366;  // matches span several events: count per year instead of per day
  const key = byYear ? (d) => +d.slice(0, 4) - +dates[0].slice(0, 4) : (d) => toDay(d) - a;
  const span = (byYear ? +dates[dates.length - 1].slice(0, 4) - +dates[0].slice(0, 4) : z - a) + 1;
  const bins = Math.min(span, byYear ? span : 40);
  const counts = new Array(bins).fill(0);
  for (const d of dates) counts[Math.min(bins - 1, Math.floor(key(d) / span * bins))]++;
  const max = Math.max(...counts), W = 600, H = 46, bw = W / bins;
  const bars = counts.map((c, i) => c ? `<rect class="bar" x="${(i * bw + 1).toFixed(1)}" y="${(H - (c / max) * H).toFixed(1)}" width="${Math.max(2, bw - 2).toFixed(1)}" height="${((c / max) * H).toFixed(1)}"><title>${c} passage${c > 1 ? "s" : ""}</title></rect>` : "").join("");
  const lab = (d) => (byYear ? d.slice(0, 4) : longDate(d));
  return `<div class="timeline" aria-label="When matching passages were published">
    <svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" role="img"><title>Matching passages by publication ${byYear ? "year" : "date"}</title>${bars}</svg>
    <div class="axis"><span>${esc(lab(dates[0]))}</span><span>${esc(lab(dates[dates.length - 1]))}</span></div></div>`;
}

function matchedCollection() {
  if (last.f.col) return colById[last.f.col];
  const counts = {};
  for (const e of last.evidence) counts[e.chunk.page.collection] = (counts[e.chunk.page.collection] || 0) + 1;
  const [id, n] = Object.entries(counts).sort((a, b) => b[1] - a[1])[0] || [];
  return n >= Math.max(2, Math.floor(last.evidence.length / 2)) ? colById[id] : null;
}

function render() {
  const { q, res, evidence } = last;
  if (!evidence.length) {
    results.innerHTML = `<div class="note">No passages matched <b>${esc(q)}</b>. Try period vocabulary (e.g. "wireless" rather than "radio"), surnames, place names, or remove filters.</div>`;
    return;
  }
  const terms = new Set(res.qterms.map((t) => t.term));
  const papers = new Set(evidence.map((e) => e.chunk.page.paper));
  const places = new Set(evidence.map((e) => e.chunk.page.place).filter(Boolean));
  const dates = evidence.map((e) => e.chunk.page.date).sort();
  const expansions = res.qterms.filter((t) => t.weight < 1).map((t) => t.term);
  const low = evidence.filter((e) => e.chunk.quality < 0.7 && e.chunk.page.src !== "headline").map((e) => e.n);
  const shown = order === "date" ? [...evidence].sort((a, b) => a.chunk.page.date.localeCompare(b.chunk.page.date)) : evidence;
  const col = matchedCollection();

  results.innerHTML = `
  <div class="layout">
    <section class="brief" aria-labelledby="brief-h">
      <div class="kicker">Evidence brief</div>
      <h2 id="brief-h">${esc(q)}</h2>
      <p class="coverage">${evidence.length} passages from <b>${papers.size}</b> newspaper${papers.size > 1 ? "s" : ""}${places.size ? ` in ${places.size} place${places.size > 1 ? "s" : ""}` : ""}, published ${esc(longDate(dates[0]))}${dates[0] !== dates[dates.length - 1] ? ` to ${esc(longDate(dates[dates.length - 1]))}` : ""}.
      Every line below is quoted verbatim from the sources; nothing is generated.</p>
      ${timelineSVG(res.allMatches)}
      <p class="small muted sans">Bars: the top ${res.allMatches.length} matching passages by publication date.${expansions.length ? ` Also matched likely OCR misreadings: <i>${esc(expansions.slice(0, 8).join(", "))}</i>.` : ""}</p>
      ${low.length ? `<div class="note">Passage${low.length > 1 ? "s" : ""} ${low.join(", ")} ha${low.length > 1 ? "ve" : "s"} noisy OCR. Check the scan before quoting.</div>` : ""}
      <div class="sans small" style="display:flex;gap:14px;flex-wrap:wrap;margin:10px 0">
        <span>Order:</span>
        <label><input type="radio" name="order" value="relevance" ${order === "relevance" ? "checked" : ""}> relevance</label>
        <label><input type="radio" name="order" value="date" ${order === "date" ? "checked" : ""}> date published</label>
        <a href="#" id="copy-all">Copy all citations</a>
        <a href="#" id="dl-csv">Download CSV</a>
      </div>
      ${shown.map((e) => evCard(e, terms)).join("")}
    </section>
    <aside>
      ${col ? `<div class="box"><div class="kicker">${col.group === "India desk" ? "About this source" : "Historical context"}</div><h3>${esc(col.title)}</h3><p>${esc(col.context)}</p>
        <p class="small"><b>Reading notes.</b> ${esc(col.reading_notes || "")}</p>
        <p class="small"><a href="collections.html#${col.id}">About this collection and its newspapers</a></p></div>` : ""}
      ${col && col.questions ? `<div class="box"><h3>Follow-up questions</h3><div class="chips">${col.questions.map((x) => `<button type="button" class="chip" data-q="${esc(x)}" data-c="${col.id}">${esc(x)}</button>`).join("")}</div></div>` : ""}
      <div class="box"><h3>Reading these results</h3><ul>
        <li>Newspapers report what was believed <i>that day</i>. First reports are often wrong.</li>
        <li>Many small papers reprinted the same wire story, so agreement is not always independent confirmation.</li>
        <li>OCR errors are common. Open the scan before you quote.</li>
        <li>Language and views reflect their time and can be offensive.</li></ul>
        <p class="small"><a href="method.html#reading">More on reading historical newspapers</a></p></div>
    </aside>
  </div>`;
}

function evCard(e, terms) {
  const p = e.chunk.page;
  const crop = scanCrop(p, e.chunk.bbox);
  const first = [...terms][0] || "";
  const isIA = p.src === "ia" || p.src === "gazette";
  const orig = isIA ? `${p.url}?q=${encodeURIComponent(first)}` : p.url;
  const linkText = p.src === "headline" ? `Read the article at ${hostOf(p.url)}`
    : isIA ? "Open the issue at the Internet Archive" : p.src === "loc" ? "Original page at the Library of Congress" : "Original";
  return `<article class="ev" data-id="${e.chunk.id}">
    <div class="meta"><span class="n">${e.n}</span><span class="paper">${esc(p.paper)}</span>
      <span class="where">${esc(p.place)}${p.place ? " · " : ""}${esc(longDate(p.date))}${p.seq ? ` · image ${p.seq}` : ""}</span>
      <span class="badge">${esc(SOURCE_LABEL[p.src] || p.src)}</span>${p.sec ? `<span class="badge">${esc(p.sec)}</span>` : ""}${qualityMeter(e.chunk.quality, p.src)}</div>
    <blockquote>${highlight(e.quote, terms)}</blockquote>
    <div class="actions">
      ${p.src === "headline" ? "" : `<button type="button" data-act="full">Full passage</button>`}
      ${crop ? `<button type="button" data-act="scan">Show scan</button>` : ""}
      <a href="${esc(orig)}" target="_blank" rel="noopener">${esc(linkText)}</a>
      <button type="button" data-act="cite">Copy citation</button>
    </div>
    <div class="slot"></div>
  </article>`;
}

results.addEventListener("change", (e) => {
  if (e.target.name === "order") { order = e.target.value; render(); }
});

results.addEventListener("click", async (e) => {
  const a = e.target.closest("#copy-all, #dl-csv");
  if (a) {
    e.preventDefault();
    if (a.id === "copy-all") {
      const txt = last.evidence.map((x) => `[${x.n}] ${citation(x.chunk.page, x.chunk)}`).join("\n");
      await navigator.clipboard.writeText(txt).catch(() => {});
      a.textContent = "Copied";
    } else {
      const rows = [["n", "newspaper", "place", "date", "image", "source", "ocr_quality", "quote", "url"]];
      for (const x of last.evidence) {
        const p = x.chunk.page;
        rows.push([x.n, p.paper, p.place, p.date, p.seq ?? "", SOURCE_LABEL[p.src], x.chunk.quality, x.quote, p.url]);
      }
      const csv = rows.map((r) => r.map((v) => `"${String(v).replace(/"/g, '""')}"`).join(",")).join("\n");
      const link = Object.assign(document.createElement("a"), { href: URL.createObjectURL(new Blob([csv], { type: "text/csv" })), download: "time-capsule-evidence.csv" });
      link.click();
    }
    return;
  }
  const btn = e.target.closest("button[data-act]");
  if (!btn) return;
  const card = btn.closest(".ev");
  const chunk = archive.chunks[+card.dataset.id];
  const slot = card.querySelector(".slot");
  const act = btn.dataset.act;
  if (act === "cite") {
    await navigator.clipboard.writeText(citation(chunk.page, chunk)).catch(() => {});
    btn.textContent = "Copied";
    setTimeout(() => (btn.textContent = "Copy citation"), 1500);
  } else if (act === "full") {
    const open = slot.dataset.kind === "full";
    slot.dataset.kind = open ? "" : "full";
    slot.innerHTML = open ? "" : `<div class="full">${highlight(chunk.text, new Set(last.res.qterms.map((t) => t.term)))}</div>`;
  } else if (act === "scan") {
    const open = slot.dataset.kind === "scan";
    slot.dataset.kind = open ? "" : "scan";
    slot.innerHTML = open ? "" : `<figure class="scan"><img loading="lazy" src="${esc(scanCrop(chunk.page, chunk.bbox))}" alt="Scan of this passage as printed in ${esc(chunk.page.paper)}, ${esc(longDate(chunk.page.date))}">
      <figcaption>The printed region this passage was read from (Library of Congress IIIF image service).</figcaption></figure>`;
  }
});

init().catch((err) => setStatus(`Could not load the archive: ${esc(err.message)}`));
