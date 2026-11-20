// In-browser retrieval over the archive. Mirrors timecapsule/retrieval (text.py,
// bm25.py, __init__.py) and the extractive brief in timecapsule/rag.py, so the
// website and the Python tools rank passages the same way.

const STOPWORDS = new Set(`a about above after again against all am an and any are as at be because been before being below
between both but by can could did do does doing down during each few for from further had has have
having he her here hers herself him himself his how i if in into is it its itself just me more most my
myself no nor not now of off on once only or other our ours ourselves out over own same she should so
some such than that the their theirs them themselves then there these they this those through to too
under until up very was we were what when where which while who whom why will with would you your
yours yourself yourselves said also upon shall
का के की को में से पर है हैं और या यह इस एक भी तथा द्वारा लिए किया गया था थे`.split(/\s+/));
const TOKEN = /[a-z0-9\u0900-\u0963\u0966-\u0d7f\u0621-\u064a\u0660-\u0669\u0679-\u06d3]+/g;

// Research-question framing words: dropped from queries only (see text.py).
const QUESTION_WORDS = new Set(`report reports reported reporting describe described say says newspaper newspapers paper papers
press coverage covered first later happen happened tell told`.split(/\s+/));

const ALPHABET = "abcdefghijklmnopqrstuvwxyz";
const OCR_CONFUSIONS = [
  ["m", "rn"], ["rn", "m"], ["h", "li"], ["li", "h"], ["d", "cl"], ["cl", "d"], ["w", "vv"],
  ["vv", "w"], ["u", "ii"], ["ii", "u"], ["e", "c"], ["c", "e"], ["o", "c"], ["c", "o"],
  ["i", "l"], ["l", "i"], ["l", "1"], ["1", "l"], ["o", "0"], ["0", "o"], ["n", "u"], ["u", "n"],
  ["s", "f"], ["f", "s"], ["t", "f"], ["f", "t"], ["b", "h"], ["h", "b"], ["a", "n"], ["n", "a"],
];
const GENERIC_EDIT_MIN_LEN = 7;
const EXPANSION_WEIGHT = 0.5;
const MAX_EXPANSIONS = 6;
const MAX_VARIANT_DF_RATIO = 0.34;
const K1 = 1.2, B = 0.75;

export function fold(text) {
  return text.replace(/ſ/g, "s").toLowerCase().normalize("NFKD").replace(/[̀-ͯ]/g, "");
}

export function stem(w) {
  if (w.length <= 3) return w;
  if (w.endsWith("ies") && !w.endsWith("eies") && !w.endsWith("aies")) return w.slice(0, -3) + "y";
  if (w.endsWith("es") && !w.endsWith("aes") && !w.endsWith("ees") && !w.endsWith("oes")) return w.slice(0, -1);
  if (w.endsWith("s") && !w.endsWith("us") && !w.endsWith("ss")) return w.slice(0, -1);
  return w;
}

export function rawTokens(text) {
  return (fold(text).match(TOKEN) || []).filter((t) => t.length > 1 && !STOPWORDS.has(t));
}

export const tokenize = (text) => rawTokens(text).map(stem);

export function queryTokens(text) {
  const toks = rawTokens(text);
  const content = toks.filter((t) => !QUESTION_WORDS.has(t));
  return content.length ? content : toks;
}

export function variants(word) {
  const out = new Set();
  const n = word.length;
  if (n >= GENERIC_EDIT_MIN_LEN) {
    for (let i = 0; i <= n; i++) {
      for (const c of ALPHABET) out.add(word.slice(0, i) + c + word.slice(i));
      if (i < n) {
        out.add(word.slice(0, i) + word.slice(i + 1));
        for (const c of ALPHABET) out.add(word.slice(0, i) + c + word.slice(i + 1));
      }
      if (i < n - 1) out.add(word.slice(0, i) + word[i + 1] + word[i] + word.slice(i + 2));
    }
  }
  for (const [a, b] of OCR_CONFUSIONS) {
    let s = word.indexOf(a);
    while (s !== -1) {
      out.add(word.slice(0, s) + b + word.slice(s + a.length));
      s = word.indexOf(a, s + 1);
    }
  }
  out.delete(word);
  return out;
}

export class Archive {
  constructor() {
    this.pages = [];   // page metadata
    this.chunks = [];  // {page, text, bbox, quality, collection}
    this.postings = new Map(); // term -> [docIds], parallel tfs in this.tfs
    this.tfs = new Map();
    this.lengths = [];
  }

  addShard(collectionId, shard) {
    const base = this.pages.length;
    for (const p of shard.pages) this.pages.push({ ...p, collection: collectionId });
    for (const [pi, text, bbox, quality] of shard.chunks) {
      const id = this.chunks.length;
      this.chunks.push({ id, page: this.pages[base + pi], text, bbox, quality });
      const counts = new Map();
      const toks = tokenize(text);
      for (const t of toks) counts.set(t, (counts.get(t) || 0) + 1);
      this.lengths.push(toks.length);
      for (const [t, tf] of counts) {
        let d = this.postings.get(t);
        if (!d) { d = []; this.postings.set(t, d); this.tfs.set(t, []); }
        d.push(id);
        this.tfs.get(t).push(tf);
      }
    }
    this.avgdl = this.lengths.reduce((a, b) => a + b, 0) / Math.max(1, this.lengths.length);
  }

  df(t) { const d = this.postings.get(t); return d ? d.length : 0; }

  idf(t) {
    const df = this.df(t), n = this.chunks.length;
    return df ? Math.log(1 + (n - df + 0.5) / (df + 0.5)) : 0;
  }

  expand(query, fuzzy = true) {
    const terms = new Map();
    for (const raw of queryTokens(query)) {
      const t = stem(raw);
      terms.set(t, { term: t, weight: 1, origin: raw });
      if (!fuzzy || raw.length < 5 || /^\d+$/.test(raw) || !/^[\x00-\x7f]+$/.test(raw)) continue;
      const dfT = this.df(t);
      const cands = [];
      for (const v of variants(raw)) {
        const sv = stem(v);
        if (sv === t || terms.has(sv) || !this.postings.has(sv)) continue;
        const dfV = this.df(sv);
        if (dfT && dfV >= MAX_VARIANT_DF_RATIO * dfT) continue;
        cands.push([dfV, sv]);
      }
      cands.sort((a, b) => b[0] - a[0] || (b[1] < a[1] ? -1 : 1));
      for (const [, sv] of cands.slice(0, MAX_EXPANSIONS)) terms.set(sv, { term: sv, weight: EXPANSION_WEIGHT, origin: raw });
    }
    return [...terms.values()];
  }

  search(query, { k = 10, filter = () => true, perPage = 2, perPaper = 4, fuzzy = true } = {}) {
    const qterms = this.expand(query, fuzzy);
    const origins = new Set(qterms.map((q) => q.origin)).size || 1;
    const scores = new Map(), matched = new Map();
    for (const q of qterms) {
      const docs = this.postings.get(q.term);
      if (!docs) continue;
      const tfs = this.tfs.get(q.term), idf = this.idf(q.term);
      for (let i = 0; i < docs.length; i++) {
        const d = docs[i];
        if (!filter(this.chunks[d])) continue;
        const tf = tfs[i], dl = this.lengths[d];
        const s = q.weight * idf * tf * (K1 + 1) / (tf + K1 * (1 - B + B * dl / this.avgdl));
        scores.set(d, (scores.get(d) || 0) + s);
        let m = matched.get(d); if (!m) { m = new Set(); matched.set(d, m); }
        m.add(q.origin);
      }
    }
    const ranked = [];
    for (const [d, s] of scores) {
      const coverage = matched.get(d).size / origins;
      ranked.push([d, s * (0.5 + 0.5 * coverage) * (0.6 + 0.4 * this.chunks[d].quality)]);
    }
    ranked.sort((a, b) => b[1] - a[1]);
    const total = ranked.length;
    // diversity: cap passages per page and per newspaper
    const pages = new Map(), papers = new Map(), out = [], overflow = [];
    for (const [d, s] of ranked.slice(0, 400)) {
      const c = this.chunks[d];
      const pk = c.page.id, nk = c.page.paper;
      if ((pages.get(pk) || 0) >= perPage || (papers.get(nk) || 0) >= perPaper) { overflow.push({ chunk: c, score: s }); continue; }
      pages.set(pk, (pages.get(pk) || 0) + 1); papers.set(nk, (papers.get(nk) || 0) + 1);
      out.push({ chunk: c, score: s });
      if (out.length === k) break;
    }
    const hits = out.concat(overflow).slice(0, k);
    return { hits, qterms, total, allMatches: ranked.slice(0, 400).map(([d]) => this.chunks[d]) };
  }
}

const SENT_SPLIT = /(?<=[.!?])["']?\s+(?=["'A-Z])|(?<=[\u0964\u0965])\s+/;

export function bestSentence(text, weights, maxWords = 60) {
  const sents = text.replace(/\n/g, " ").split(SENT_SPLIT).map((s) => s.trim()).filter((s) => s.split(/\s+/).length >= 4);
  if (!sents.length) return text.split(/\s+/).slice(0, maxWords).join(" ");
  let bi = 0, best = -1;
  sents.forEach((s, i) => {
    const toks = new Set(tokenize(s));
    let sc = 0;
    for (const [t, w] of weights) if (toks.has(t)) sc += w;
    sc /= Math.sqrt(s.split(/\s+/).length + 5);
    if (sc > best) { best = sc; bi = i; }
  });
  let quote = sents[bi];
  if (quote.split(/\s+/).length < 18 && bi + 1 < sents.length) quote += " " + sents[bi + 1];
  const words = quote.split(/\s+/);
  return words.slice(0, maxWords).join(" ") + (words.length > maxWords ? " ..." : "");
}
