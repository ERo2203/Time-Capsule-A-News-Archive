import json
import zipfile

from timecapsule.chunking import chunk_page
from timecapsule.ocr.clean import quality_score
from timecapsule.rag import ResearchAssistant
from timecapsule.sources.headlines import fetch, outlet_for
from timecapsule.models import Page
from timecapsule.retrieval.text import tokenize


def test_outlet_matching_prefers_longest_domain():
    assert outlet_for("timesofindia.indiatimes.com") == ("The Times of India", "Mumbai")
    assert outlet_for("mumbaimirror.indiatimes.com") == ("Mumbai Mirror", "Mumbai")
    assert outlet_for("www.thehindu.com") == ("The Hindu", "Chennai")
    assert outlet_for("gadgets.ndtv.com") == ("NDTV", "New Delhi")
    assert outlet_for("someblog.in") == ("someblog.in", "")  # .in counts as Indian
    assert outlet_for("nytimes.com") is None


def test_headline_import_keeps_indian_outlets_from_zip(tmp_path):
    recs = [
        {"topic": "NATION", "link": "https://www.ndtv.com/a", "domain": "ndtv.com",
         "published_date": "2020-08-07 21:00:00", "title": "Plane skids off runway at Kozhikode", "lang": "en"},
        {"topic": "WORLD", "link": "https://www.bbc.co.uk/b", "domain": "bbc.co.uk",
         "published_date": "2020-08-07 21:00:00", "title": "Something else", "lang": "en"},
    ]
    z = tmp_path / "Source Provider.zip"
    with zipfile.ZipFile(z, "w") as f:
        f.writestr("Source Provider/myData.json", json.dumps(recs))
        f.writestr("__MACOSX/Source Provider/._myData.json", "junk")
    pages = list(fetch(z, collection="india"))
    assert [p.newspaper for p in pages] == ["NDTV"]
    p = pages[0]
    assert (p.source, p.date, p.section, p.url) == ("headline", "2020-08-07", "Nation", "https://www.ndtv.com/a")
    chunks = chunk_page(p)  # headlines are short but still one full-quality passage
    assert len(chunks) == 1 and chunks[0].quality == 1.0 and chunks[0].text == p.text


def test_hindi_is_tokenized_with_vowel_signs_kept():
    toks = tokenize("भारतीय स्टेट बैंक ने भारतीय रिज़र्व बैंक के अनुमोदन से।")
    assert toks == ["भारतीय", "स्टेट", "बैंक", "ने", "भारतीय", "रिज़र्व", "बैंक", "अनुमोदन"]


def test_indic_quality_is_not_penalized_as_noise():
    hindi = "बैंककारी विनियमन अधिनियम 1949 की धारा 35 के निबंधनानुसार भारतीय स्टेट बैंक ने भारतीय रिज़र्व बैंक के अनुमोदन से"
    assert quality_score(hindi) > 0.9


def test_bilingual_gazette_search_in_hindi():
    text = ("Notice under the Banking Regulation Act. " * 20 +
            "ये विनियम बैंक अधिकारी कर्मचारी ( सेवानिवृत्ति के पश्चात् निजी क्षेत्र की संस्थाओं में नियोजन की स्वीकृति ) "
            "विनियम, 2000 कहलाए जाएंगे । " + "Reserve Bank of India list of securities. " * 20)
    page = Page(id="gazette:x", source="gazette", newspaper="The Gazette of India", date="2000-09-30", url="u", text=text)
    ra = ResearchAssistant(chunk_page(page))
    ans = ra.ask("सेवानिवृत्ति के पश्चात् नियोजन", k=1)
    assert "सेवानिवृत्ति" in ans.evidence[0].quote
