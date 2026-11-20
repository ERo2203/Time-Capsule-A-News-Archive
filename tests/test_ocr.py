from timecapsule.chunking import chunk_page
from timecapsule.models import Block, Chunk, Page
from timecapsule.ocr.alto import parse_alto
from timecapsule.ocr.clean import clean_ocr_text, quality_score

ALTO = """<?xml version="1.0" encoding="UTF-8"?>
<alto xmlns="http://www.loc.gov/standards/alto/ns-v2#">
 <Layout><Page ID="P1" WIDTH="1000" HEIGHT="2000">
  <PrintSpace>
   <TextBlock ID="B1" HPOS="100" VPOS="200" WIDTH="300" HEIGHT="100">
    <TextLine HPOS="100" VPOS="200" WIDTH="300" HEIGHT="40">
     <String CONTENT="The" WC="0.9"/><SP/><String CONTENT="steamer" WC="0.8"/><SP/><String CONTENT="Car" WC="0.7"/><HYP CONTENT="-"/>
    </TextLine>
    <TextLine HPOS="100" VPOS="250" WIDTH="280" HEIGHT="40">
     <String CONTENT="pathia" WC="0.7"/><SP/><String CONTENT="arrived." WC="1.0"/>
    </TextLine>
   </TextBlock>
  </PrintSpace>
 </Page></Layout>
</alto>"""


def test_parse_alto_joins_hyphens_and_keeps_layout():
    blocks, conf = parse_alto(ALTO)
    assert len(blocks) == 1
    b = blocks[0]
    assert b.text == "The steamer\nCarpathia arrived."
    # line union: x 100..400, y 200..290 on a 1000x2000 page
    assert b.bbox == (10.0, 10.0, 30.0, 4.5)
    assert 0.7 < conf < 0.95


def test_clean_ocr_text_repairs_layout_damage():
    raw = "The Preſident's car-\nriage was ſeen......\n|||| ~~ ||\nat the theatre"
    out = clean_ocr_text(raw)
    assert "President's carriage" in out
    assert "seen." in out and "....." not in out
    assert "||||" not in out


def test_quality_score_separates_text_from_noise():
    good = "The news that Secretary Seward is still alive will mitigate in some degree the horror of the nation."
    bad = "tr sunick'irr tiircittjiu*- •irnir -itarn* Kuiuul ,.»«*3e:i^«rtt abyurd tho ill-fa t&lt;?ii"
    assert quality_score(good) > 0.85
    assert quality_score(bad) < quality_score(good) - 0.25


def test_chunk_page_keeps_citation_and_box():
    words = " ".join(["word"] * 60)
    page = Page(id="loc:x", source="loc", newspaper="Evening star", date="1912-04-16", url="https://example",
                place="Washington, D.C.", page=3, iiif="https://iiif/x",
                blocks=[Block("HEADLINE HERE", (10, 10, 20, 2), 0.9), Block(words + ".", (10, 12, 20, 20), 0.8)])
    chunks = chunk_page(page)
    assert len(chunks) == 1  # short headline merged into the article below it
    c = chunks[0]
    assert c.text.startswith("HEADLINE HERE")
    assert c.bbox == (10, 10, 20, 22)
    assert c.citation() == "Evening star, Washington, D.C., 1912-04-16, p. 3"
    assert c.scan_crop_url() == "https://iiif/x/pct:10.00,10.00,20.00,22.00/pct:50/0/default.jpg"


def test_plain_text_pages_are_windowed_with_overlap():
    text = " ".join(f"w{i}." if i % 20 == 19 else f"w{i}" for i in range(400))
    page = Page(id="ia:x", source="ia", newspaper="Daily", date="1918-10-01", url="u", text=text)
    chunks = chunk_page(page)
    assert len(chunks) >= 3
    assert all(isinstance(c, Chunk) and c.bbox is None for c in chunks)
    first, second = chunks[0].text.split(), chunks[1].text.split()
    assert set(first[-10:]) & set(second[:40])  # overlap keeps sentences intact across cuts
