#!/usr/bin/env python3
"""Parse a docling DocTags file (kidney biopsy pathology report) into JSON.

The input holds three DocTags documents concatenated, one per test, always in
this order:
    page 1 -> "elektronmikroskop"        (EPON block, toluidine blue semithin
                                          section, ultrastructural findings)
    page 2 -> "lysmikroskop"             (structured table)
    page 3 -> "immunpatologiske_funn"    (immunology, a code block)

Each page is parsed on its own, so values from one page can never overwrite
values from another.

Rules for how tolerant the parser is:
  * Labels must be spelled correctly. A misspelled label gives None for that
    field, silently (a separate test checks the fields afterwards).
  * Wherever a Norwegian character (å, ø, æ) is expected, up to 3 arbitrary
    characters are accepted in its place, with a warning.
  * Any character that is not plain ASCII or å/ø/æ gives a warning.
  * ref_nr: first occurrence of the header "Ref.nr" wins. Warns if the number
    of occurrences differs from the number of pages, or if the values differ.

Usage:  python serialize3.py input.txt [output.json]
Warnings go to stderr, the JSON goes to the output file.
"""
import json
import re
import sys
from collections import Counter
from datetime import datetime


# --------------------------------------------------------------------------- #
# Step 1: generate all fields (every value starts as None)
# --------------------------------------------------------------------------- #
def build_schema():
    return {
        # Header (read once, from page 1)
        "ref_nr": None,                    # str, first header "Ref.nr" found on any page
        "prøven_tatt": None,               # ISO datetime string
        "rapportert": None,                # ISO datetime string

        # Page 1
        "elektronmikroskop": {
            "epon_block_status": None,     # True = EM gjennomført, False = ikke EM / ikke rep

            # Toluidinblått farget semitynnsnitt (light microscopy of the EM block)
            "toluidinblått": {
                "kortex": None,            # bool (påvist, or a number, gives True)
                "medulla": None,           # bool
                "glomeruli": None,         # int
                "vurderbare_glomeruli": None,  # int
                # Antall glomeruli med:
                "nekroser": None,          # int
                "halvmåner": None,         # int (total crescents)
                "segmental": None,         # int (segmental sclerosis)
                "global": None,            # int (global sclerosis)
                "iskemi": None,            # int
            },

            # Ultrastrukturelle funn
            "ultrastrukturelle_funn": {
                "nedslag": None,           # bool, derived: any of the four deposit types checked
                "subepitelial": None,      # bool (X = True, blank = False)
                "intramembranos": None,    # bool
                "subendotelial": None,     # bool
                "mesangial": None,         # bool
                "fotprosessfusjon": None,  # False | "Global" | "Segmental"
                "basalmembran": None,      # False | "Global" | "Segmental"
            },
        },

        # Page 2 (structured table)
        "lysmikroskop": {
            "kortex": None,                # bool
            "medulla": None,               # bool
            "glomeruli": None,             # int
            # Antall glomeruli med:
            "global": None,                # int
            "nekroser": None,              # int
            "cellular": None,              # int
            "fibrocellular": None,         # int
            "fibrous": None,               # int
            "halvmåner": None,             # int, sum of the three crescent types
            "segmental": None,             # int
            "iskemi": None,                # int
            "arterier": None,              # int
            "arteriosklerose": None,       # "None" | "Low" | "Moderate" | "High"
            "arteriehyalinose": None,      # same scale
            "tubulusatrofi": None,         # same scale
            "interstitiell": None,         # same scale
            "interstitiell_percent": None, # int/float percentage
        },

        # Page 3 (code block)
        "immunpatologiske_funn": {
            "metode": None,                # str
            "iga": None,                   # "-", "+", "++", "+++"
            "igm": None,
            "igg": None,
            "c1q": None,
            "c3": None,
            "lette_kjeder": None,          # str, e.g. "lik ekspresjon"
        },
    }


# --------------------------------------------------------------------------- #
# Warnings
# --------------------------------------------------------------------------- #
def warn(msg):
    print(f"WARNING: {msg}", file=sys.stderr)


# --------------------------------------------------------------------------- #
# DocTags parsing
# --------------------------------------------------------------------------- #
LOC = re.compile(r"<loc_\d+>")
# Only the element types we use. Pictures and page footers are ignored.
ELEM = re.compile(r"<(text|section_header_level_\d|code|otsl)>(.*?)</\1>", re.S)


def clean(s):
    """Strip location tags and any other tags, collapse whitespace."""
    s = LOC.sub("", s)
    s = re.sub(r"<[^>]+>", "", s)
    return re.sub(r"\s+", " ", s).strip()


def parse_doctags(raw):
    """Return a list of pages; each page is a list of (tag, content) in order."""
    pages = []
    for block in re.findall(r"<doctag>(.*?)</doctag>", raw, re.S):
        elems = []
        for m in ELEM.finditer(block):
            tag, body = m.group(1), m.group(2)
            if tag == "otsl":
                elems.append((tag, body))      # table: parsed later by parse_otsl
            elif tag == "code":
                # remove loc tags first, then the language tag e.g. <_FORTRAN_>
                elems.append((tag, re.sub(r"^<_\w+_>", "", LOC.sub("", body))))
            else:
                elems.append((tag, clean(body)))
        pages.append(elems)
    return pages


def parse_otsl(body):
    """Table body -> list of rows, each row a list of cell strings."""
    rows = []
    for row in LOC.sub("", body).split("<nl>"):
        cells = [c.strip() for c in row.split("<fcel>") if c.strip()]
        if cells:
            rows.append(cells)
    return rows


# Small accessors so the section parsers don't touch the raw tuples.
def page_text(elems):
    """All free-text lines and headers on the page, one per line."""
    return "\n".join(x for t, x in elems if t == "text" or t.startswith("section_header"))


def page_code(elems):
    return "\n".join(x for t, x in elems if t == "code")


def page_rows(elems):
    rows = []
    for t, body in elems:
        if t == "otsl":
            rows.extend(parse_otsl(body))
    return rows


# --------------------------------------------------------------------------- #
# Norwegian-tolerant matching
# --------------------------------------------------------------------------- #
# Write patterns with the CORRECT Norwegian spelling, e.g. r"\bhalvmåner".
# Every å/ø/æ in a pattern is replaced by the wildcard (.{0,3}), keeping the
# characters on both sides as anchors:   halvmåner -> halvm(.{0,3})ner
# If the wildcard captured anything other than the expected character, a
# warning is given. The match itself still counts as a match.
def expand_norwegian(pattern):
    expected = []

    def slot(m):
        name = f"nor{len(expected)}"
        expected.append(m.group(0).lower())
        return f"(?P<{name}>.{{0,3}})"

    return re.sub("[åøæÅØÆ]", slot, pattern), expected


def nsearch(pattern, text, field):
    """re.search (case-insensitive) with the Norwegian wildcard + warning."""
    expanded, expected = expand_norwegian(pattern)
    m = re.search(expanded, text, re.I)
    if m:
        for i, exp in enumerate(expected):
            got = m.group(f"nor{i}")
            if got is not None and got.lower() != exp:
                warn(f"{field}: Norwegian character '{exp}' read as {got!r}")
    return m


# Characters we expect to see: printable ASCII, whitespace and å/ø/æ.
EXPECTED_CHAR = re.compile(r"[\x20-\x7eåøæÅØÆ\s]")


def check_characters(page_no, elems):
    """Warn once per distinct unexpected character on a page."""
    text = " ".join(clean(x) if t == "otsl" else x for t, x in elems)
    odd = Counter(ch for ch in text if not EXPECTED_CHAR.fullmatch(ch))
    for ch, n in odd.items():
        warn(f"page {page_no}: unexpected character {ch!r} (U+{ord(ch):04X}) x{n}")


# --------------------------------------------------------------------------- #
# Value helpers
# --------------------------------------------------------------------------- #
def to_int(v):
    return int(v) if v is not None and re.fullmatch(r"\d+", str(v)) else None


def text_int(label, text, field):
    """Free-text line like 'halvmåner.0' -> 0. None if the label or number is missing."""
    m = nsearch(rf"\b{label}\.*[ \t]*(?P<val>\d+)", text, field)
    return int(m.group("val")) if m else None


def text_present(label, text, field):
    """True if the label is followed by 'påvist' or a number,
    False if the label is there with nothing after it, None if no label."""
    m = nsearch(rf"\b{label}\.*[ \t]*(?P<val>påvist|\d+)?", text, field)
    if not m:
        return None
    return m.group("val") is not None


def text_checked(label, text, field):
    """Checkbox-style field like 'subepitelial. X'.
    True if the label is followed by an X, False if the label is there but
    left blank, None if the label itself was not found (e.g. misspelled)."""
    m = nsearch(rf"\b{label}\.*[ \t]*(?P<val>x\b)?", text, field)
    if not m:
        return None
    return m.group("val") is not None


def table_values(rows, label, field):
    """Second column of every table row whose first column matches `label`."""
    return [r[1] for r in rows if len(r) >= 2 and nsearch(label, r[0], field)]


def table_int(rows, label, field):
    vals = table_values(rows, label, field)
    return to_int(vals[0]) if vals else None


def to_datetime(date_s, time_s):
    try:
        return datetime.strptime(f"{date_s} {time_s}", "%d.%m.%Y %H:%M").isoformat()
    except (TypeError, ValueError):
        return None


def next_texts(elems, idx, n):
    """The next n text elements after position idx (stops at a section header)."""
    out = []
    for tag, txt in elems[idx + 1:]:
        if tag == "text":
            out.append(txt)
            if len(out) == n:
                break
        elif tag.startswith("section_header"):
            break
    return out


def find_idx(elems, pred):
    for i, (tag, txt) in enumerate(elems):
        if pred(tag, txt):
            return i
    return None


# Free-text grading words (doctors choose their own wording, so this stays lenient).
DEGREES = [
    ("None",     r"ingen|ikke|normal"),
    ("Low",      r"lett|mild|liten"),
    ("Moderate", r"moderat|middels"),
    ("High",     r"uttalt|kraftig|betydelig|alvorlig|sterk|høy"),
]


def degree(word, field):
    """Map a Norwegian degree word to None/Low/Moderate/High (or None if unknown)."""
    if not word:
        return None
    for name, pattern in DEGREES:
        if nsearch(pattern, word, field):
            return name
    return None


def global_segmental(text):
    """Text after a label -> False / 'Global' / 'Segmental' / None."""
    if not text:
        return None
    t = text.lower()
    if "global" in t:
        return "Global"
    if "segment" in t:
        return "Segmental"
    if re.search(r"ingen|ikke|nei|normal", t):
        return False
    return None


# --------------------------------------------------------------------------- #
# Step 2: fill the schema, one function per part of the report
# --------------------------------------------------------------------------- #
REF_LABEL = re.compile(r"^ref\.?\s?nr\.?:?$", re.I)   # "Ref.nr:" - not "Ref.r", not "Externt ref.nr:"


def fill_ref_nr(schema, pages):
    """Collect every header ref number; first one is written. Warnings for missing fields (should be same as page numbers), or for inconsistencies (ref numbers should be the same on all pages)."""
    found = []                                         # (page number, value)
    for p, elems in enumerate(pages, 1):
        for i, (tag, txt) in enumerate(elems):
            if tag == "text" and REF_LABEL.match(txt):
                v = next_texts(elems, i, 1)
                if v:
                    found.append((p, v[0]))

    if len(found) != len(pages):
        warn(f"ref_nr: found {len(found)} header ref number(s) on pages "
             f"{[p for p, _ in found]}, but there are {len(pages)} pages")
    if len({v for _, v in found}) > 1:
        warn(f"ref_nr: inconsistent values {[v for _, v in found]}")
    schema["ref_nr"] = found[0][1] if found else None


def fill_header(schema, elems):
    """prøven_tatt / rapportert: label element followed by a date and a time element."""
    for key, label in (("prøven_tatt", r"^prøven tatt$"), ("rapportert", r"^rapportert$")):
        i = find_idx(elems, lambda t, x, l=label, k=key: t == "text" and nsearch(l, x, k))
        if i is not None:
            v = next_texts(elems, i, 2)
            if len(v) == 2:
                schema[key] = to_datetime(v[0], v[1])


def fill_elektronmikroskop(sec, elems):
    text = page_text(elems)
    P = "elektronmikroskop."

    # --- EPON block status: read from the line starting with "status" ---
    m = re.search(r"\bstatus\.*[ \t]*(?P<line>[^\n]*)", text, re.I)
    if m:
        line = m.group("line")
        if re.search(r"\bikke\s+(?:EM|rep)", line, re.I):
            sec["epon_block_status"] = False
        elif nsearch(r"\bEM gjennomført", line, P + "epon_block_status"):
            sec["epon_block_status"] = True

    # --- Toluidinblått farget semitynnsnitt ---
    t = sec["toluidinblått"]
    Pt = P + "toluidinblått."
    t["kortex"] = text_present("kortex", text, Pt + "kortex")
    t["medulla"] = text_present("medulla", text, Pt + "medulla")
    t["glomeruli"] = text_int("Antall glomeruli", text, Pt + "glomeruli")
    t["vurderbare_glomeruli"] = text_int("Antall vurderbare glomeruli", text, Pt + "vurderbare_glomeruli")
    t["nekroser"] = text_int("kun nekrose", text, Pt + "nekroser")
    t["halvmåner"] = text_int("halvmåner", text, Pt + "halvmåner")
    t["segmental"] = text_int("segmental sklerose", text, Pt + "segmental")
    t["global"] = text_int("global sklerose", text, Pt + "global")
    t["iskemi"] = text_int("iskemi", text, Pt + "iskemi")

    # --- Ultrastrukturelle funn ---
    u = sec["ultrastrukturelle_funn"]
    Pu = P + "ultrastrukturelle_funn."
    # X after the label = deposits of that type; blank = none. A misspelled label gives None.
    u["subepitelial"] = text_checked("subepitelial", text, Pu + "subepitelial")
    u["intramembranos"] = text_checked("intramembranøs", text, Pu + "intramembranos")
    u["subendotelial"] = text_checked("subendotelial", text, Pu + "subendotelial")
    u["mesangial"] = text_checked("mesangial", text, Pu + "mesangial")   # \b makes "mmesangial" fail

    # nedslag is derived: True if any of the four is checked. False only if all
    # four were read and are blank; if a field is missing we cannot say, so None.
    checks = [u[k] for k in ("subepitelial", "intramembranos", "subendotelial", "mesangial")]
    if any(c is True for c in checks):
        u["nedslag"] = True
    elif all(c is False for c in checks):
        u["nedslag"] = False

    # label followed by free text -> Global / Segmental / False
    m = nsearch(r"\bFotprosessfusjon\.*[ \t]*(?P<val>[^\n]*)", text, Pu + "fotprosessfusjon")
    u["fotprosessfusjon"] = global_segmental(m.group("val")) if m else None
    m = nsearch(r"\bBasalmembran\.*[ \t]*(?P<val>[^\n]*)", text, Pu + "basalmembran")
    u["basalmembran"] = global_segmental(m.group("val")) if m else None


def fill_lysmikroskop(sec, elems):
    rows = page_rows(elems)          # each row: [parameter, value]
    P = "lysmikroskop."

    # The row "Kortex | Medulla" sits under the "Påvist" header: listed = present.
    cells = {c.lower() for r in rows for c in r}
    if "kortex" in cells:
        sec["kortex"] = True
    if "medulla" in cells:
        sec["medulla"] = True

    # --- glomeruli counts ---
    sec["glomeruli"] = table_int(rows, r"^Antall glomeruli$", P + "glomeruli")
    sec["global"] = table_int(rows, r"\bglobal sklerose", P + "global")
    sec["nekroser"] = table_int(rows, r"\bkun nekrose", P + "nekroser")
    sec["cellular"] = table_int(rows, r"\bmed cellulære halvmåner", P + "cellular")
    sec["fibrocellular"] = table_int(rows, r"\bmed fibrocellulære halvmåner", P + "fibrocellular")
    sec["fibrous"] = table_int(rows, r"\bmed fibrøse halvmåner", P + "fibrous")
    sec["segmental"] = table_int(rows, r"\bsegmental sklerose", P + "segmental")
    sec["iskemi"] = table_int(rows, r"\biskemisk", P + "iskemi")

    # Total crescents = sum of the three types. If any type is missing the
    # total would be misleading, so it stays None.
    subs = [sec["cellular"], sec["fibrocellular"], sec["fibrous"]]
    if all(s is not None for s in subs):
        sec["halvmåner"] = sum(subs)

    # --- arteries / tubulointerstitium ---
    sec["arterier"] = table_int(rows, r"^Antall arterier", P + "arterier")
    for key, label in (("arteriosklerose", r"^Arteriosklerose$"),
                       ("arteriehyalinose", r"^Arteriehyalinose$"),
                       ("tubulusatrofi", r"^Tubulusatrofi$")):
        vals = table_values(rows, label, P + key)
        sec[key] = degree(vals[0], P + key) if vals else None

    # "Interstitiell fibrose" appears as two rows: a grade word and a percentage.
    for v in table_values(rows, r"^Interstitiell fibrose$", P + "interstitiell"):
        if re.fullmatch(r"\d+(\.\d+)?\s*%?", v):
            num = v.rstrip("% ")
            sec["interstitiell_percent"] = float(num) if "." in num else int(num)
        else:
            sec["interstitiell"] = degree(v, P + "interstitiell")


def fill_immunpatologi(sec, elems):
    code = page_code(elems)
    P = "immunpatologiske_funn."

    # --- method ---
    if nsearch(r"\bImmunhistokjemi\b", code, P + "metode"):
        sec["metode"] = "Immunhistokjemi"
    elif nsearch(r"\bImmunfluorescens\b", code, P + "metode"):
        sec["metode"] = "Immunfluorescens"

    # --- one line per marker, e.g. "... IgM. +"  ->  "+"  ("..." means empty) ---
    labels = {"iga": r"IgA", "igm": r"IgM", "igg": r"IgG", "c1q": r"C1q", "c3": r"C3"}
    for line in code.splitlines():
        line = line.replace("\u2212", "-").replace("\u2013", "-").strip()
        for key, label in labels.items():
            m = re.match(rf"^\W*{label}\b\.*\s*(?P<rest>.*)$", line, re.I)
            if m:
                rest = m.group("rest").replace("...", "").replace("…", "").strip()
                s = re.match(r"(\+{1,3}|-)(?=\s|$)", rest)
                sec[key] = s.group(1) if s else None
        m = re.match(r"^\W*lette kjeder\b\.*\s*(?P<rest>.*)$", line, re.I)
        if m:
            v = m.group("rest").replace("...", "").replace("…", "").strip(" .")
            sec["lette_kjeder"] = v or None


# Page order -> section name and the function that fills it.
SECTIONS = [
    ("elektronmikroskop", fill_elektronmikroskop),
    ("lysmikroskop", fill_lysmikroskop),
    ("immunpatologiske_funn", fill_immunpatologi),
]


def fill_schema(schema, pages):
    if len(pages) != len(SECTIONS):
        warn(f"expected {len(SECTIONS)} pages, found {len(pages)}")

    for n, elems in enumerate(pages, 1):
        check_characters(n, elems)

    if pages:
        fill_header(schema, pages[0])
    fill_ref_nr(schema, pages)

    # Pages are assigned to sections by position.
    for (name, fill), elems in zip(SECTIONS, pages):
        fill(schema[name], elems)
    return schema


def main():
    if len(sys.argv) < 2:
        sys.exit("Usage: python serialize3.py input.txt [output.json]")
    raw = open(sys.argv[1], encoding="utf-8").read()
    out = sys.argv[2] if len(sys.argv) > 2 else "output.json"

    schema = build_schema()                           # 1) generate all fields
    result = fill_schema(schema, parse_doctags(raw))  # 2) fill them in

    with open(out, "w", encoding="utf-8") as fh:
        json.dump(result, fh, ensure_ascii=False, indent=2)
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()