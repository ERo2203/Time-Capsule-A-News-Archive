"""Command line: ``timecapsule harvest | ocr | build | ask | serve``."""

from __future__ import annotations

import argparse
import json
import sys
import textwrap
from pathlib import Path


def _assistant(args):
    from .harvest import load_collections
    from .rag import ResearchAssistant
    from .store import load_chunks

    return ResearchAssistant(load_chunks(Path(args.corpus)), load_collections(), dense=args.dense)


def _filters(args):
    from .retrieval import Filters

    return Filters(start=args.date_from, end=args.date_to, collections=args.collection or [],
                   sources=args.source or [], min_quality=args.min_quality)


def cmd_harvest(args):
    from .harvest import harvest

    harvest(only=args.only, loc_pages=args.loc_pages, ia_issues=args.ia_issues,
            out_dir=Path(args.corpus), force=args.force)


def cmd_ocr(args):
    from .sources.local_scans import fetch
    from .store import write_jsonl

    out = Path(args.corpus) / f"pages-local-{args.collection or Path(args.folder).name}.jsonl.gz"
    pages = []
    for p in fetch(args.folder, lang=args.lang, collection=args.collection or ""):
        print(f"  ocr {p.id}: {len(p.blocks)} blocks, confidence {p.ocr_confidence}")
        pages.append(p.to_dict())
    print(f"saved {write_jsonl(out, pages)} pages -> {out}  (now run `timecapsule build`)")


def cmd_build(args):
    from .build import build

    build(Path(args.corpus), Path(args.site_data))


def cmd_ask(args):
    ra = _assistant(args)
    ans = ra.ask(args.question, k=args.k, filters=_filters(args),
                 mode="claude" if args.claude else "extractive", model=args.model)
    if args.json:
        print(json.dumps({
            "question": ans.question,
            "written": ans.written,
            "coverage": ans.coverage,
            "collection": ans.collection and ans.collection["id"],
            "notes": ans.notes,
            "evidence": [{"n": e.n, "quote": e.quote, "citation": e.chunk.citation(), "url": e.chunk.url,
                          "scan": e.chunk.scan_crop_url(), "quality": e.chunk.quality,
                          "passage": e.chunk.text} for e in ans.evidence],
        }, indent=2, ensure_ascii=False))
        return
    w = textwrap.TextWrapper(width=100, initial_indent="    ", subsequent_indent="    ")
    print(f"\nQ: {ans.question}\n")
    if ans.written:
        print(textwrap.fill(ans.written, 100, replace_whitespace=False) + "\n")
    cov = ans.coverage
    if cov["passages"]:
        print(f"Evidence: {cov['passages']} passages from {cov['newspapers']} newspapers, "
              f"{cov['first_date']} to {cov['last_date']}\n")
    for e in sorted(ans.evidence, key=lambda e: e.chunk.date):
        print(f"[{e.n}] {e.chunk.citation()}  (OCR quality {e.chunk.quality:.2f})")
        print(w.fill(f'"{e.quote}"'))
        print(f"    {e.chunk.url}")
        if e.chunk.scan_crop_url():
            print(f"    scan: {e.chunk.scan_crop_url()}")
        print()
    if ans.collection:
        print(f"Context - {ans.collection['title']}:")
        print(w.fill(ans.collection["context"]))
    for n in ans.notes:
        print(f"note: {n}")


def cmd_serve(args):
    try:
        from flask import Flask, jsonify, request
    except ImportError:
        sys.exit('serve needs: pip install "timecapsule[serve]"')
    from .retrieval import Filters

    ra = _assistant(args)
    app = Flask(__name__)

    @app.post("/api/ask")
    def ask():
        body = request.get_json(force=True)
        f = Filters(start=body.get("from"), end=body.get("to"), collections=body.get("collections", []),
                    sources=body.get("sources", []))
        ans = ra.ask(body["question"], k=int(body.get("k", 8)), filters=f,
                     mode="claude" if body.get("claude") else "extractive")
        return jsonify({
            "written": ans.written, "coverage": ans.coverage, "notes": ans.notes,
            "context": ans.collection,
            "evidence": [{"n": e.n, "quote": e.quote, "citation": e.chunk.citation(), "url": e.chunk.url,
                          "scan": e.chunk.scan_crop_url(), "quality": e.chunk.quality} for e in ans.evidence],
        })

    app.run(host=args.host, port=args.port)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="timecapsule", description=__doc__)
    ap.add_argument("--corpus", default="data/corpus", help="corpus directory")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("harvest", help="download OCR for the collections in corpus/collections.json")
    p.add_argument("--only", nargs="*", help="collection ids")
    p.add_argument("--loc-pages", type=int, default=12)
    p.add_argument("--ia-issues", type=int, default=4)
    p.add_argument("--force", action="store_true")
    p.set_defaults(func=cmd_harvest)

    p = sub.add_parser("ocr", help="OCR a folder of your own newspaper scans with Tesseract")
    p.add_argument("folder")
    p.add_argument("--collection")
    p.add_argument("--lang", default="eng", help="Tesseract language code(s), e.g. eng+fra")
    p.set_defaults(func=cmd_ocr)

    p = sub.add_parser("build", help="chunk pages and export the website data")
    p.add_argument("--site-data", default="site/data")
    p.set_defaults(func=cmd_build)

    for name, fn, hlp in (("ask", cmd_ask, "ask a research question"), ("serve", cmd_serve, "run a JSON API")):
        p = sub.add_parser(name, help=hlp)
        if name == "ask":
            p.add_argument("question")
            p.add_argument("-k", type=int, default=8)
            p.add_argument("--collection", nargs="*")
            p.add_argument("--from", dest="date_from")
            p.add_argument("--to", dest="date_to")
            p.add_argument("--source", nargs="*", choices=["loc", "ia", "local"])
            p.add_argument("--min-quality", type=float, default=0.0)
            p.add_argument("--claude", action="store_true", help="also write an answer with Claude (needs [llm])")
            p.add_argument("--model", default="claude-opus-5-5")
            p.add_argument("--json", action="store_true")
        else:
            p.add_argument("--host", default="127.0.0.1")
            p.add_argument("--port", type=int, default=5000)
        p.add_argument("--dense", action="store_true", help="add embedding retrieval (needs [dense])")
        p.set_defaults(func=fn)

    args = ap.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
