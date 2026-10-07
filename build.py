#!/usr/bin/env python3
"""Build index.html: a browsable list of every ctext Wiki book.

Data: api.ctext.org/gettexttitles (all Wiki items) + the ctext Data Wiki RDF
dump (authors, dynasties, catalogue categories). Both cached in cache/.
English titles come from titles_en.tsv (made by translate.py). The page is
English only: no Chinese characters end up in index.html (asserted below).
Run with the venv python (needs pypinyin):  .venv/bin/python build.py
Delete cache/ to refresh the data.
"""
import collections, json, re, unicodedata, urllib.parse, urllib.request, zipfile
from pathlib import Path
from pypinyin import lazy_pinyin, Style
from translate import norm

HERE = Path(__file__).parent
CACHE = HERE / "cache"

# 四庫 catalogue categories -> (English, branch). Branches: the four 四庫 divisions.
CATS = {
    "易": ("Book of Changes", "Classics"), "書": ("Book of Documents", "Classics"),
    "詩": ("Book of Poetry", "Classics"), "禮": ("Rites", "Classics"),
    "春秋": ("Spring and Autumn Annals", "Classics"), "孝經": ("Classic of Filial Piety", "Classics"),
    "五經總義": ("The Classics in general", "Classics"), "經解": ("The Classics in general", "Classics"),
    "四書": ("Four Books", "Classics"), "論語": ("Analects", "Classics"),
    "樂": ("Music", "Classics"), "小學": ("Philology & dictionaries", "Classics"),
    "正史": ("Official dynastic histories", "History"), "編年": ("Chronicles", "History"),
    "紀事本末": ("Topical histories", "History"), "別史": ("Unofficial histories", "History"),
    "雜史": ("Miscellaneous histories", "History"), "詔令奏議": ("Edicts & memorials", "History"),
    "傳記": ("Biographies", "History"), "史鈔": ("History digests", "History"),
    "史抄": ("History digests", "History"), "載記": ("Regional states", "History"),
    "霸史": ("Regional states", "History"), "時令": ("Seasons & calendar customs", "History"),
    "地理": ("Geography & gazetteers", "History"), "職官": ("Government offices", "History"),
    "政書": ("Statecraft & institutions", "History"), "儀注": ("Ritual protocol", "History"),
    "刑法": ("Law", "History"), "故事": ("Precedents", "History"),
    "目錄": ("Bibliographies", "History"), "金石": ("Inscriptions on bronze & stone", "History"),
    "史評": ("Historical criticism", "History"), "譜牒": ("Genealogies", "History"),
    "儒家": ("Confucian thought", "Thought & Sciences"), "兵家": ("Military", "Thought & Sciences"),
    "兵書": ("Military", "Thought & Sciences"), "法家": ("Legalism", "Thought & Sciences"),
    "農家": ("Agriculture", "Thought & Sciences"), "醫家": ("Medicine", "Thought & Sciences"),
    "醫書": ("Medicine", "Thought & Sciences"), "天文算法": ("Astronomy & mathematics", "Thought & Sciences"),
    "天文": ("Astronomy & mathematics", "Thought & Sciences"), "歷算": ("Astronomy & mathematics", "Thought & Sciences"),
    "術數": ("Divination & numerology", "Thought & Sciences"), "五行": ("Divination & numerology", "Thought & Sciences"),
    "藝術": ("Arts: painting, calligraphy, music, games", "Thought & Sciences"),
    "雜藝術": ("Arts: painting, calligraphy, music, games", "Thought & Sciences"),
    "譜錄": ("Catalogues of things: inkstones, plants, food…", "Thought & Sciences"),
    "雜家": ("Miscellaneous writers", "Thought & Sciences"), "雜家類": ("Miscellaneous writers", "Thought & Sciences"),
    "雜家類雜考之屬": ("Miscellaneous writers", "Thought & Sciences"),
    "類書": ("Encyclopedias", "Thought & Sciences"), "類事": ("Encyclopedias", "Thought & Sciences"),
    "小說家": ("Anecdotes & fiction", "Thought & Sciences"), "小說": ("Anecdotes & fiction", "Thought & Sciences"),
    "釋家": ("Buddhism", "Thought & Sciences"), "道家": ("Daoism", "Thought & Sciences"),
    "道家附釋氏神仙類凡": ("Daoism", "Thought & Sciences"), "墨家": ("Mohism", "Thought & Sciences"),
    "墨家類": ("Mohism", "Thought & Sciences"), "縱橫家": ("Diplomatic strategists", "Thought & Sciences"),
    "楚辭": ("Songs of Chu", "Literature"), "別集": ("Collected works of one author", "Literature"),
    "總集": ("Anthologies", "Literature"), "詩文評": ("Literary criticism", "Literature"),
    "文史": ("Literary criticism", "Literature"), "詞曲": ("Song lyrics & drama", "Literature"),
}

# Title endings -> what kind of book it probably is. First match wins, so longer endings first.
KINDS = [
    ("縣志", "County gazetteer"), ("府志", "Prefecture gazetteer"), ("州志", "Department gazetteer"),
    ("志", "Gazetteer or treatise"), ("詩集", "Poetry collection"), ("文集", "Prose collection"),
    ("集", "Collected works"), ("詩", "Poems"), ("詞", "Song lyrics"), ("錄", "Records"),
    ("記", "Accounts"), ("傳", "Biographies & tales"), ("譜", "Genealogy or register"),
    ("經", "Classic or scripture"), ("考", "Studies"), ("論", "Essays"), ("注", "Commentary"),
    ("註", "Commentary"), ("疏", "Sub-commentary"), ("解", "Explanations"), ("圖", "Illustrated"),
    ("方", "Medical prescriptions"), ("稿", "Drafts"), ("史", "History"), ("鈔", "Excerpts"),
    ("編", "Compilation"), ("說", "Discourses"), ("略", "Outline"), ("義", "Meanings"),
]

# Periods for the timeline: (label, from year, to year). Negative = BCE.
PERIODS = [
    ("Pre-Qin", -1100, -221), ("Qin & Han", -221, 220), ("Six Dynasties", 220, 581),
    ("Sui & Tang", 581, 907), ("Five Dynasties", 907, 960), ("Song", 960, 1279),
    ("Yuan", 1279, 1368), ("Ming", 1368, 1644), ("Qing", 1644, 1912), ("Modern", 1912, 2100),
]
DYNASTY_PERIOD = {
    "周": 0, "秦": 1, "漢": 1, "東漢": 1, "西漢": 1, "曹魏": 2, "孫吳": 2, "蜀漢": 2, "西晉": 2,
    "東晉": 2, "劉宋": 2, "南齊": 2, "南梁": 2, "南陳": 2, "北魏": 2, "北齊": 2, "北周": 2,
    "隋": 3, "唐": 3, "南唐": 4, "後蜀": 4, "後晉": 4, "後唐": 4, "後漢": 4, "後周": 4,
    "宋": 5, "遼": 5, "金": 5, "元": 6, "明": 7, "清": 8,
}


def fetch(url, path):
    if not path.exists():
        print("downloading", url)
        CACHE.mkdir(exist_ok=True)
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        path.write_bytes(urllib.request.urlopen(req, timeout=120).read())
    return path


def latest_dump_url():
    html = urllib.request.urlopen(urllib.request.Request(
        "https://ctext.org/tools/linked-open-data", headers={"User-Agent": "Mozilla/5.0"})).read().decode()
    urls = re.findall(r'https://download\.ctext\.org/download/datawiki/ctext_datawiki-[\d-]+\.ttl\.zip', html)
    return max(urls)  # file names sort by date


def period_of_year(y):
    for i, (_, a, b) in enumerate(PERIODS):
        if a <= y < b:
            return i
    return -1


CJK = re.compile(r"[\u3000-\u303f\u3400-\u9fff\uf900-\ufaff\uff00-\uffef\U00020000-\U0003ffff]")
COMPOUND_SURNAMES = {"歐陽", "司馬", "諸葛", "上官", "司徒", "夏侯", "皇甫", "公孫", "令狐", "長孫", "宇文",
                     "慕容", "尉遲", "東方", "澹臺", "鍾離", "申屠", "獨孤", "端木", "聞人", "呼延", "軒轅"}
SURNAME_READING = {"曾": "zeng", "單": "shan", "樂": "yue", "解": "xie", "查": "zha", "仇": "qiu",
                   "區": "ou", "繆": "miao", "蓋": "ge", "覃": "qin", "冼": "xian", "召": "shao"}


def syllables(s):
    return lazy_pinyin(s, style=Style.NORMAL, v_to_u=True, errors="ignore")


def romanize_title(s):  # fallback only, for a title with no usable English
    return " ".join(w.capitalize() for w in syllables(s)) or "Untitled"


def romanize_name(s):  # 戚繼光 -> Qi Jiguang
    if not CJK.search(s):
        return s
    n = 2 if s[:2] in COMPOUND_SURNAMES else 1
    sur = SURNAME_READING.get(s[:1]) if n == 1 else None
    sur = sur or "".join(syllables(s[:n]))
    given = "".join(syllables(s[n:]))
    return " ".join(w.capitalize() for w in (sur, given) if w) or "Unknown"


def english(s):  # NFKC turns full-width punctuation into ASCII; anything still CJK is unusable
    s = unicodedata.normalize("NFKC", s).strip()
    return "" if CJK.search(s) else s


def main():
    titles = json.loads(fetch("https://api.ctext.org/gettexttitles", CACHE / "titles.json").read_text())
    zpath = CACHE / "datawiki.ttl.zip"
    if not zpath.exists():
        fetch(latest_dump_url(), zpath)
    z = zipfile.ZipFile(zpath)
    ttl_name = z.namelist()[0]
    ttl = z.read(ttl_name).decode()
    dump_date = re.search(r"\d{4}-\d\d-\d\d", ttl_name).group(0)

    # --- parse the dump: one regex for claims, one for category qualifiers ---
    typ, claims, label = {}, collections.defaultdict(list), {}
    for e, p, v in re.findall(r'^ctext:(\d+) claim:([\w-]+) (.+?) ;$', ttl, re.M):
        v = v.strip('"')
        if p == "type":
            typ[e] = v
        else:
            claims[e].append((p, v))
    label = dict(re.findall(r'^ctext:(\d+) rdfs:label "(.*)" \.$', ttl, re.M))
    cats_of = collections.defaultdict(list)
    for e, body in re.findall(r'^ctext:(\d+) claim:indexed-in ctext:\d+ ;\n\s+cstat:indexed-in \[(.*?)\]', ttl, re.M | re.S):
        cats_of[e] += [c for c in re.findall(r'cqual:stated-category "([^"]+)"', body) if c in CATS]

    work_by_wb, works_by_name = {}, collections.defaultdict(list)
    for e, t in typ.items():
        if t != "work":
            continue
        for p, v in claims[e]:
            if p == "ctext-work" and v.startswith("ctp:work:wb"):
                work_by_wb[int(v[len("ctp:work:wb"):])] = e
            elif p == "name":
                works_by_name[v].append(e)

    def first(e, prop):
        return next((v for p, v in claims[e] if p == prop), None)

    # --- people (only those who wrote something in the list) ---
    people, person_idx = [], {}

    def person(e):
        if e in person_idx:
            return person_idx[e]
        name = first(e, "name") or label.get(e, "?")
        per = -1
        dyn = first(e, "associated-dynasty")
        if dyn:
            per = DYNASTY_PERIOD.get(label.get(dyn.split(":")[1], ""), -1)
        if per < 0:
            y = first(e, "died") or first(e, "born")
            if y and re.fullmatch(r"-?\d+", y):
                per = period_of_year(int(y) - (0 if first(e, "died") else -30))
        en = first(e, "link-wikipedia_en") or ""
        person_idx[e] = len(people)
        people.append([name, "", per, en, int(e)])
        return person_idx[e]

    cat_list = sorted({v for v in CATS.values()}, key=lambda c: (c[1], c[0]))
    cat_idx = {c: i for i, c in enumerate(cat_list)}

    # --- group Wiki items by title (repeated titles = editions) ---
    groups = collections.defaultdict(list)
    for b in titles["books"]:
        if b["urn"].startswith("ctp:wb"):
            groups[b["title"]].append(int(b["urn"][len("ctp:wb"):]))

    books = []
    for title, res in groups.items():
        res.sort()
        w = next((work_by_wb[r] for r in res if r in work_by_wb), None)
        if w is None and works_by_name.get(title):
            cands = works_by_name[title]
            w = next((c for c in cands if first(c, "creator")), cands[0])
        auth = cat = per = -1
        en = ""
        if w:
            c = first(w, "creator")
            if c:
                auth = person(c.split(":")[1])
                per = people[auth][2]
            if cats_of[w]:
                cat = cat_idx[CATS[collections.Counter(cats_of[w]).most_common(1)[0][0]]]
            en = first(w, "link-wikipedia_en") or ""
        kind = next((i for i, (suf, _) in enumerate(KINDS) if title.endswith(suf)), -1)
        en_title = urllib.parse.unquote(en.rsplit("/", 1)[-1]).replace("_", " ") if en else ""
        books.append([title, "", res if len(res) > 1 else res[0], auth, cat, kind, per,
                      en_title, int(w) if w else 0])

    data = {
        "date": dump_date,
        "cats": [[en, br] for en, br in cat_list],
        "kinds": [en for _, en in KINDS],
        "periods": [p[0] for p in PERIODS],
        "people": people,
        "books": books,
    }

    # --- self-check: fails loudly if the join or the links break ---
    n_items = sum(len(r) for r in groups.values())
    assert 45000 < n_items < 60000, n_items
    jx = next(b for b in books if b[0] == "紀效新書")
    assert jx[2] == 3 or 3 in jx[2], jx
    assert people[jx[3]][0] == "戚繼光" and data["periods"][jx[6]] == "Ming" and jx[7] == "Jixiao Xinshu", jx
    assert data["cats"][books[[b[0] for b in books].index("武經總要")][4]][0] == "Military"

    # input for translate.py: [title, author, subject, period, english-from-wikipedia]
    (CACHE / "books.json").write_text(json.dumps([
        [b[0], people[b[3]][0] if b[3] >= 0 else "", data["cats"][b[4]][0] if b[4] >= 0 else "",
         data["periods"][b[6]] if b[6] >= 0 else "", b[7]] for b in books], ensure_ascii=False))

    # --- English-only public data: drop every Chinese string ---
    tsv = HERE / "titles_en.tsv"
    en_titles = {norm(t): e for t, _, e in (l.partition("\t") for l in tsv.read_text().splitlines())} if tsv.exists() else {}

    def en_person(p):  # Wikipedia's English name when there is one, else romanized
        wiki = urllib.parse.unquote(p[3].rsplit("/", 1)[-1]).replace("_", " ") if p[3] else ""
        return english(re.sub(r"\s*\(.*\)$", "", wiki)) or romanize_name(p[0])

    pub_books = []
    for b in books:
        if english(b[7]):
            en, mt = english(b[7]), 0             # name of the English Wikipedia article
        elif english(en_titles.get(norm(b[0]), "")):
            en, mt = english(en_titles[norm(b[0])]), 1  # machine translation
        else:
            en, mt = romanize_title(b[0]), 2      # no translation yet: romanized
        pub_books.append([en, b[2], b[3], b[4], b[5], b[6], mt, b[8]])
    data["people"] = [[en_person(p), p[2], p[3], p[4]] for p in people]
    data["books"] = pub_books
    jx_pub = pub_books[[b[0] for b in books].index("紀效新書")]
    assert jx_pub[0] == "Jixiao Xinshu" and data["people"][jx_pub[2]][0] == "Qi Jiguang", jx_pub

    # site-wide figures from ctext (numbers only) and the count of review corrections
    st = json.loads(fetch("https://api.ctext.org/getstats", CACHE / "stats.json").read_text())
    num = lambda k: int(st[k]["value"])
    data["ctext"] = {"wikiChars": num("contribchars"), "libraryPages": num("docrespages"),
                     "dbChars": num("chartotal") + num("chartotal_posthan"),
                     "parallels": num("paralleltotal"), "date": st["statupdate"]["value"][:10]}
    log = HERE / "review_changes.tsv"
    data["fixed"] = len(log.read_text().splitlines()) if log.exists() else 0

    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    html = (HERE / "template.html").read_text().replace("/*DATA*/null", payload)
    assert not CJK.search(html), CJK.search(html)  # English-only page
    (HERE / "index.html").write_text(html)
    mt = collections.Counter(b[6] for b in pub_books)
    print(f"{n_items} Wiki items -> {len(books)} titles; {sum(b[3] >= 0 for b in books)} with author, "
          f"{sum(b[4] >= 0 for b in books)} with category; English titles: {mt[0]} Wikipedia, {mt[1]} machine, "
          f"{mt[2]} romanized only; index.html {len(html) / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
