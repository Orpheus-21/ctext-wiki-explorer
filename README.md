# ctext Wiki Explorer

A single web page that lists every book in the Wiki of the Chinese Text Project (ctext.org) with an English title.

Open the site: https://orpheus-21.github.io/ctext-wiki-explorer/

## What it does

The ctext Wiki holds about 49,500 digitized editions of pre-modern Chinese books. The ctext site shows them page by page and only in Chinese. This project puts all of them on one page in English. The page groups repeated editions of one title into one entry, so the page shows about 38,600 books.

Each entry shows:

* An English title. Most English titles are machine translations. A small `MT` mark shows these titles.
* The author, with the name in pinyin.
* The period, the subject from the old imperial library catalogues, and the kind of book.
* A link to each edition on ctext.org. The text on ctext.org is in Chinese.
* A link to the Data Wiki record and to English Wikipedia, when they exist.

On the page, you can:

* Search in English. The search looks at the title, the author, the subject, the period and the kind of book. Every word must match.
* Filter by subject, by period and by kind of book. Each filter shows the number of matching books.
* Show only famous books. A famous book or its author has an English Wikipedia article.
* Click an author to see all books by that author.
* Click "Surprise me" to get a random book from the current list.
* Sort by the amount of information, at random, from A to Z, or by the number of editions.

The page contains no Chinese characters.

## Requirements

* Python 3. The scripts were tested with Python 3.14.
* The Python package `pypinyin`, version 0.55 or later. Only `build.py` needs it.
* An internet connection for the first build. `build.py` downloads about 12 MB from ctext.org.
* To make or check English titles: the `claude` command-line tool, logged in. Only `translate.py` and `review.py` need it.
* A web browser to open the page.

## Install

1. Clone the repo:

   ```
   git clone https://github.com/Orpheus-21/ctext-wiki-explorer.git
   cd ctext-wiki-explorer
   ```

2. Make a virtual environment:

   ```
   python3 -m venv .venv
   ```

3. Install the dependency:

   ```
   .venv/bin/pip install -r requirements.txt
   ```

## Usage

### Open the page

Open the site address in a web browser. GitHub Pages serves `index.html` from the `main` branch.

To use the page offline, open `index.html` in a web browser. The repo contains a built copy.

### Build the page

Run the build:

```
.venv/bin/python build.py
```

The script writes `index.html`. It also writes `cache/books.json`, which `translate.py` and `review.py` read.

To get new data from ctext.org, delete the `cache/` folder. Then run the build again.

### Translate titles

`translate.py` gives an English title to each title that has none. Run `build.py` once before you run `translate.py`.

| Command | Result |
|---|---|
| `python3 translate.py --test` | Translates one sample batch. Shows the token use and 30 samples. |
| `python3 translate.py 5` | Translates the next 5 batches of 500 titles. |
| `python3 translate.py` | Translates all titles that have no English title. |

The script appends each result to `titles_en.tsv`. If a run stops, run the same command again. The script continues with the remaining titles.

### Check titles

`review.py` compares each English title with its Chinese title. It changes only the titles that are wrong.

```
python3 review.py 2
```

The number is the count of batches of 500 titles. The default is 1. The script writes the corrections into `titles_en.tsv` and adds each change to `review_changes.tsv`.

After a translation run or a check, run `build.py` again to put the new titles on the page.

## Files

| File | Content |
|---|---|
| `build.py` | Downloads the data, joins it, and writes `index.html`. |
| `template.html` | The page layout, styles and script. `build.py` puts the data into it. |
| `translate.py` | Makes English titles in batches. |
| `review.py` | Checks and corrects English titles in batches. |
| `titles_en.tsv` | One line per title: the Chinese title, a tab, the English title. |
| `review_changes.tsv` | One line per correction: the Chinese title, the old English title, the new English title. |
| `index.html` | The built page. |
| `cache/` | Downloaded data and run state. Git ignores this folder. |

## How it works

`build.py` uses two sources from ctext.org:

1. The API function `gettexttitles`. It gives the title and the identifier of each Wiki item.
2. The Data Wiki dump in RDF format. It gives works, authors, dynasties, dates and catalogue subjects.

The script joins each Wiki item to a work in the dump. It uses the work identifier first and the exact title second. Items that have the same title become one entry. The script finds the kind of book from the last characters of the Chinese title. It finds the period from the dynasty or the dates of the author.

The English title of an entry comes from one of three sources, in this order:

1. The name of the English Wikipedia article of the work.
2. The line in `titles_en.tsv`.
3. A pinyin form of the Chinese title. The page marks these titles with `ROM`.

The author name comes from the English Wikipedia article of the author. If no article exists, the script makes the name from pinyin.

The script then removes all Chinese text from the data and puts the data into `template.html`. The build stops with an error if a Chinese character is in the result.

`translate.py` and `review.py` send each batch to the `claude` command-line tool as one new request. The tool must return the Chinese title with each English title. A script keeps a reply line only when the returned title matches a title in the batch. This rule stops a skipped line from putting a translation on the wrong title. Titles are compared after Unicode NFKC normalization and with whitespace removed.

## Limits

* The English titles are machine translations. Some are wrong. `review.py` corrects a part of them.
* About 23 percent of the books have an author in the data. About 19 percent have a subject.
* Automatic pinyin can choose the wrong reading of a character with two readings.

## License

The code is licensed under the GNU General Public License, version 3 or any later version. See the `LICENSE` file.

The data comes from the Chinese Text Project. The Data Wiki data is licensed under the Creative Commons Attribution, NonCommercial, ShareAlike 3.0 license (CC BY-NC-SA 3.0). This license also applies to `index.html`, `titles_en.tsv` and `review_changes.tsv`, because they contain this data. You must credit the Chinese Text Project, you must not use the data for commercial purposes, and you must share changes under the same license.

This project is not affiliated with the Chinese Text Project.
