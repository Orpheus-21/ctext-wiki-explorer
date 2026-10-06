#!/usr/bin/env python3
"""Give every Wiki title an English title, in batches sent to `claude -p`.

Titles only, never book contents. Reads cache/books.json (written by build.py),
appends to titles_en.tsv (Chinese<TAB>English), and skips titles already there,
so rerunning resumes. Stops cleanly when the CLI fails (e.g. usage limit).

  python3 translate.py --test     one sample batch, prints tokens and samples
  python3 translate.py            everything left (Military first)
  python3 translate.py 5          only the next 5 batches
"""
import json, random, re, subprocess, sys, unicodedata
from pathlib import Path

HERE = Path(__file__).parent
OUT = HERE / "titles_en.tsv"
BATCH = 500

PROMPT = """You translate titles of pre-modern Chinese books into English for a beginner-friendly catalogue.
Input lines: n<TAB>title<TAB>author<TAB>subject<TAB>period (author/subject/period may be empty).
Reply with ONLY lines: n<TAB>title copied exactly<TAB>English title. Exactly 3 fields; do NOT repeat author, subject or period. One line per input line, no notes, no blank lines.
Rules: translate the meaning, at most 10 words, Title Case. Keep proper names in pinyin without tone marks
(people, places, studios/pen names, reign eras), e.g. 嘉靖高陵縣志 -> Gaoling County Gazetteer (Jiajing Era),
某某堂集 -> Collected Works from the Moumou Hall. Use the standard English name for famous works.
If a title is opaque, give your best literal reading; never skip a line."""


def done():
    if not OUT.exists():
        return set()
    return {norm(l.split("\t", 1)[0]) for l in OUT.read_text().splitlines() if "\t" in l}


def norm(t):  # model rewrites compatibility ideographs (e.g. U+FA67 逸) and drops stray whitespace/control chars
    return re.sub(r"[\s\x00-\x1f]", "", unicodedata.normalize("NFKC", t))


def ask(rows, prompt, effort):
    """Send rows (first field = Chinese title) to claude -p; return {title: last field of reply}, tokens, usage."""
    lines = "\n".join(f"{i}\t" + "\t".join(re.sub(r"[\s\x00-\x1f]+", " ", x).strip() for x in r) for i, r in enumerate(rows))
    p = subprocess.run(
        ["claude", "-p", "--model", "sonnet", "--effort", effort, "--tools", "",
         "--system-prompt", prompt, "--setting-sources", "project", "--settings", '{"disableAllHooks":true}',
         "--strict-mcp-config", "--disable-slash-commands", "--no-session-persistence",
         "--output-format", "json"],
        input=lines, capture_output=True, text=True, timeout=900)
    try:
        res = json.loads(p.stdout)
    except json.JSONDecodeError:
        res = {"is_error": True, "result": (p.stdout + p.stderr)[-500:]}
    if p.returncode or res.get("is_error"):
        sys.exit(f"claude failed (usage limit?), rerun later:\n{res.get('result')}")
    titles = {norm(r[0]): r[0] for r in rows}
    got = {}
    (HERE / "cache" / "last_reply.txt").write_text(res["result"])
    for line in res["result"].splitlines():  # keep only lines whose echoed title matches, so a skipped line can't shift the rest
        parts = line.split("\t")
        if len(parts) > 3:  # model sometimes echoes the whole input row: n, title, author, subject, period, English
            parts = [parts[0], parts[1], parts[-1]]
        elif len(parts) < 3:  # or uses spaces instead of tabs
            m = re.match(r"\s*\d+\s+(\S+)\s+(.+?)\s*$", line)
            parts = ["", *m.groups()] if m else []
        if len(parts) == 3 and norm(parts[1]) in titles and parts[2].strip():
            got[titles[norm(parts[1])]] = parts[2].strip()
    u = res.get("usage", {})
    tokens = sum(u.get(k, 0) for k in ("input_tokens", "cache_creation_input_tokens",
                                        "cache_read_input_tokens", "output_tokens"))
    return got, tokens, u


def run_batch(rows):
    got, tokens, u = ask([r[:4] for r in rows], PROMPT, "low")
    if len(got) < 0.9 * len(rows):
        print(f"warning: only {len(got)}/{len(rows)} lines matched; raw reply in cache/last_reply.txt", flush=True)
    with OUT.open("a") as f:  # titles are stored as one line, so their own tabs/newlines become spaces
        f.writelines(f"{re.sub(r'[\t\n]', ' ', t)}\t{e}\n" for t, e in got.items())
    return got, tokens, u


def main():
    books = json.loads((HERE / "cache" / "books.json").read_text())
    have = done()
    todo = [b for b in books if not b[4] and norm(b[0]) not in have]
    with OUT.open("a") as f:  # a few ctext titles are already English: keep them as they are
        for b in [b for b in todo if not re.search(r"[\u3400-\u9fff\U00020000-\U0003ffff\uf900-\ufaff]", b[0])]:
            f.write(f"{re.sub(r'[\t\n]', ' ', b[0])}\t{b[0].strip().splitlines()[-1].strip()}\n")
            todo.remove(b)
    left = len(todo)
    print(f"{left} titles left")
    if "--test" in sys.argv:
        known = [b for b in todo if b[0] in ("紀效新書", "武經總要")]
        todo = known + random.Random(1).sample([b for b in todo if b not in known], BATCH - len(known))
        got, tokens, u = run_batch(todo)
        print(f"translated {len(got)}/{len(todo)}; tokens this batch {tokens}: {u}")
        print(f"projected total for all titles: ~{tokens * (left / BATCH) / 1e6:.2f}M tokens")
        for t in list(got)[:2] + random.Random(2).sample(list(got)[2:], min(28, len(got) - 2)):
            print(f"  {t}  ->  {got[t]}")
        return
    todo.sort(key=lambda b: (b[2] != "Military", not b[1], not b[2]))  # Military, then most info first
    total = 0
    limit = next((int(a) for a in sys.argv[1:] if a.isdigit()), None)
    for s in range(0, len(todo), BATCH)[:limit]:
        got, tokens, _ = run_batch(todo[s:s + BATCH])
        total += tokens
        print(f"batch {s // BATCH + 1}/{-(-len(todo) // BATCH)}: {len(got)} titles, {tokens} tokens (run total {total})", flush=True)


if __name__ == "__main__":
    main()
