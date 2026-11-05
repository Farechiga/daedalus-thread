"""Reading ICARUS data.jsonl records into flat Python dicts."""
import json
from urllib.parse import urlparse

# ref/url host -> source database (the 19 harvested collections listed on the Zenodo record).
# Note: meta/collection is the *holding institution* (e.g. "Musée du Louvre"), not this.
SOURCES = {
    "artemis.uni-muenchen.de": ("artemis", "Artemis (LMU München)", "DE"),
    "www.bildindex.de": ("bildindex", "Bildindex der Kunst & Architektur", "DE"),
    "corpusvitrearum.de": ("cvma", "Corpus Vitrearum Deutschland", "DE"),
    "heartfield.adk.de": ("heartfield", "Heartfield Online (AdK)", "DE"),
    "datenbank.museum-kassel.de": ("kassel", "Hessen Kassel Heritage", "DE"),
    "inkunabeln.digitale-sammlungen.de": ("bsb_ink", "Incunabula Catalogue, Bavarian State Library", "DE"),
    "www.museen.thueringen.de": ("thueringen", "Museen Thüringen", "DE"),
    "sammlung.staedelmuseum.de": ("staedel", "Städel Museum", "DE"),
    "www.virtuelles-kupferstichkabinett.de": ("vkk", "Virtuelles Kupferstichkabinett", "DE"),
    "digital.belvedere.at": ("belvedere", "Austrian Gallery Belvedere", "AT"),
    "realonline.imareal.sbg.ac.at": ("realonline", "REALonline (IMAREAL)", "AT"),
    "vitrosearch.ch": ("vitrosearch", "Vitrosearch", "CH"),
    "pauart.pl": ("pauart", "PAUart (Polish Academy of Arts and Sciences)", "PL"),
    "manuscripts.kb.nl": ("kb_mss", "Medieval Illuminated Manuscripts (KB)", "NL"),
    "www.rijksmuseum.nl": ("rijksmuseum", "Rijksmuseum", "NL"),
    "rkd.nl": ("rkd", "RKD – Netherlands Institute for Art History", "NL"),
    "ballads.bodleian.ox.ac.uk": ("bodleian_ballads", "Broadside Ballads Online (Bodleian)", "GB"),
    "emblematica.library.illinois.edu": ("emblematica", "Emblematica Online", "US"),
    "www.nga.gov": ("nga", "National Gallery of Art", "US"),
}

MULTI = ("meta/title", "meta/creator", "meta/time", "meta/instance_of", "meta/genre",
         "meta/collection", "meta/iconclass/original", "meta/iconclass/processed")


def _key(path):
    """meta/iconclass/processed -> iconclass_processed"""
    return path.split("/", 1)[1].replace("/", "_")


def source_of(url):
    """Return (source_id, source_name, source_country) for a record URL."""
    host = urlparse(url).netloc.lower()
    return SOURCES.get(host, ("unknown:" + host, host, None))


def iter_records(path):
    """Yield one flat dict per ICARUS record. Multi-valued fields become lists (order kept)."""
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            raw = json.loads(line)
            rec = {"id": raw["id"], "url": None, "image_path": None, "image_size": None}
            for k in MULTI:
                rec[_key(k)] = []
            for e in raw["entries"]:
                p = e["path"]
                if p == "ref/url":
                    rec["url"] = e["url"]
                elif p == "ref/image/path":
                    rec["image_path"] = e["value"]
                elif p == "ref/image/size":
                    rec["image_size"] = e["value"]
                elif p in MULTI:
                    v = e.get("value")
                    if isinstance(v, str):
                        v = v.strip()
                    if v:
                        rec[_key(p)].append(v)
            yield rec
