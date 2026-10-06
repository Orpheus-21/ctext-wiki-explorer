#!/usr/bin/env python3
"""Quality pass: check each English title against its Chinese title and fix wrong ones.

Only titles needing a fix come back from the model, so good titles cost no output.
Fixes are written into titles_en.tsv and logged (old -> new) in review_changes.tsv;
reviewed titles are listed in cache/reviewed.txt, so rerunning resumes.

  python3 review.py 1     review the next 500 titles
"""
import json, re, sys
from translate import HERE, OUT, BATCH, ask, norm

DONE = HERE / "cache" / "reviewed.txt"
LOG = HERE / "review_changes.tsv"
CJK = re.compile(r"[㐀-鿿豈-﫿\U00020000-\U0003ffff]")

PROMPT = """You check English titles of pre-modern Chinese books for accuracy against the Chinese originals.
Input lines: n<TAB>Chinese title<TAB>current English<TAB>author<TAB>subject<TAB>period (last three may be empty).
Reply ONLY for titles whose English is wrong, misleading or garbled, as lines: n<TAB>Chinese title copied exactly<TAB>corrected English.
Leave acceptable titles out entirely. If nothing needs fixing, reply with the single word NONE. No notes.
Fix: mistranslations, wrong readings of names, a person's name/pen name/posthumous title mistaken for a place or studio
(or the reverse), missing or invented meaning, any Chinese characters left in the English.
Also fix titles so literal that the sense is lost, and clumsy renderings such as a building word left in pinyin.
Rules: faithful to the Chinese, at most 12 words, Title Case. Proper names (people, places, studio/hall names, pen names,
reign eras) in pinyin without tone marks, with an apostrophe where syllables are ambiguous (Ding'an). Standard English
names for famous works.
- Building words are always translated, never romanized into the name and never doubled: 軒 Studio, 齋 Studio, 堂 Hall,
  館 Lodge, 樓 Tower, 閣 Pavilion, 室 Chamber, 山房 Mountain Studio, 草堂 Thatched Hall, 精舍 Retreat, 山莊 Mountain Villa.
  兩罍軒 -> Lianglei Studio (not Liangleixuan Studio); 海山仙館 -> Haishan Immortals' Lodge.
  When the whole name is a pen name, romanize it and add no building word: 南軒集 -> Collected Works of Nanxuan.
- Allusions and set phrases get their intended sense, not a word-by-word reading: 美芹 is a modest "humble offering",
  so 美芹十論 -> Ten Humble Discourses; 管見 -> Humble Views; 芻言 -> Rustic Words.
- Official titles are translated, never romanized as if part of a name: 修撰 Compiler, 學士 Academician, 侍郎 Vice Minister,
  待制 Academician-in-Waiting, 尚書 Minister, 檢討 Examining Editor. 歐陽修撰集 -> Collected Works of Compiler Ouyang.
- Check every line carefully; do not skim. Do not change a title that is already accurate and natural."""


def main():
    rows = [l.split("\t", 1) for l in OUT.read_text().splitlines() if "\t" in l]
    en = dict(rows)
    ctx = {norm(b[0]): b[1:4] for b in json.loads((HERE / "cache" / "books.json").read_text())}
    reviewed = set(DONE.read_text().splitlines()) if DONE.exists() else set()
    todo = [t for t, _ in rows if t not in reviewed]
    todo.sort(key=lambda t: not CJK.search(en[t]))  # broken ones (Chinese left in the English) first
    limit = next((int(a) for a in sys.argv[1:] if a.isdigit()), 1)
    total = 0
    for s in range(0, len(todo), BATCH)[:limit]:
        batch = todo[s:s + BATCH]
        got, tokens, _ = ask([[t, en[t], *ctx.get(norm(t), ["", "", ""])] for t in batch], PROMPT, "medium")
        changes = [(t, en[t], new) for t, new in got.items() if new != en[t] and not CJK.search(new)
                   and not (len(new.split()) == 1 and len(en[t].split()) > 2)]  # a lone word replacing a title is garbage (文編 -> "Ming")
        for t, _, new in changes:
            en[t] = new
        OUT.write_text("".join(f"{t}\t{en[t]}\n" for t, _ in rows))
        with LOG.open("a") as f:
            f.writelines(f"{t}\t{old}\t{new}\n" for t, old, new in changes)
        with DONE.open("a") as f:
            f.writelines(f"{t}\n" for t in batch)
        total += tokens
        print(f"reviewed {len(batch)}, fixed {len(changes)}, {tokens} tokens (run total {total}); "
              f"{len(todo) - s - len(batch)} left", flush=True)
        for t, old, new in changes:
            print(f"  {t}: {old}  ->  {new}")


if __name__ == "__main__":
    main()
