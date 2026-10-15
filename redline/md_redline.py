#!/usr/bin/env python3
"""
md_redline.py - word-level "redline" reports for Markdown files (Hebrew/RTL friendly).

Two modes:

  1) Compare two files:
       python md_redline.py compare old.md new.md [-o diff.html]

  2) Walk the Git history of a repo and report every change:
       python md_redline.py history [REPO] [-o report.html]
           [--range main~20..main] [--since 2026-09-01] [--paths "*.md" "docs/*.md"]
           [--context 1] [--oldest-first]

Without -o, the report is named <file>.changes.html (new.changes.html, or
life-story.changes.html for --paths life-story.md), or <repo>.changes.html when
history covers several files, so a single ignore rule, *.changes.html, covers them all.

Deleted words are red + struck through, inserted words are green + underlined,
shown inside the running paragraph. Each paragraph gets dir="auto", so Hebrew
paragraphs display right-to-left and English ones left-to-right.

Only uses the Python standard library (+ the `git` command for history mode).
"""

import argparse
import difflib
import html
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------- word diff

# words (any script, incl. Hebrew), runs of spaces, newlines, single punctuation marks
TOKEN_RE = re.compile(r"\n|[^\S\n]+|\w+(?:['׳״\"]\w+)*|[^\w\s]", re.UNICODE)


def tokenize(text):
    return TOKEN_RE.findall(text)


def word_diff(old, new):
    """Return a list of (op, text) with op in {'eq', 'del', 'ins'}."""
    a, b = tokenize(old), tokenize(new)
    sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
    segs = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            segs.append(["eq", "".join(a[i1:i2])])
        else:
            if i2 > i1:
                segs.append(["del", "".join(a[i1:i2])])
            if j2 > j1:
                segs.append(["ins", "".join(b[j1:j2])])
    return _merge_small_gaps(segs)


def _merge_small_gaps(segs):
    """Glue 'del x' + ' ' + 'del y' into one block so changes read as phrases."""
    out = []
    i = 0
    while i < len(segs):
        s = segs[i]
        if (s[0] == "eq" and s[1].strip() == "" and "\n" not in s[1]
                and out and out[-1][0] != "eq" and i + 1 < len(segs) and segs[i + 1][0] != "eq"):
            # whitespace between two changes: put it in both the deleted and inserted text
            dels = [x for x in out[-2:] if x[0] == "del"]
            inss = [x for x in out[-2:] if x[0] == "ins"]
            if dels:
                dels[-1][1] += s[1]
            if inss:
                inss[-1][1] += s[1]
            if not dels:
                out.append(["del", s[1]])
            if not inss:
                out.append(["ins", s[1]])
            i += 1
            continue
        # append, merging with the same kind found among the last two segments
        if s[0] != "eq":
            same = [x for x in out[-2:] if x[0] == s[0]] if out and out[-1][0] != "eq" else []
            if same:
                same[-1][1] += s[1]
                i += 1
                continue
        out.append(list(s))
        i += 1
    # order: deletions before insertions inside each change block
    final, block = [], []
    for s in out:
        if s[0] == "eq":
            final += sorted(block, key=lambda x: x[0] != "del") + [s]
            block = []
        else:
            block.append(s)
    final += sorted(block, key=lambda x: x[0] != "del")
    return [tuple(s) for s in final if s[1]]


def count_words(segs):
    d = sum(len(re.findall(r"\w+", t)) for op, t in segs if op == "del")
    n = sum(len(re.findall(r"\w+", t)) for op, t in segs if op == "ins")
    return d, n


# ---------------------------------------------------------------- rendering

def segs_to_paragraphs(segs):
    """Split segments at newlines into paragraphs of HTML."""
    paras, cur = [], []
    for op, text in segs:
        parts = text.split("\n")
        for k, part in enumerate(parts):
            if k > 0:
                paras.append("".join(cur))
                cur = []
            if part:
                esc = html.escape(part)
                cur.append(esc if op == "eq" else f"<{op}>{esc}</{op}>")
    paras.append("".join(cur))
    return paras


def render_file_diff(old, new, context=1):
    """HTML for one file: only changed paragraphs (+context), word-level marks.
    Returns (html, deleted_words, inserted_words)."""
    a, b = old.split("\n"), new.split("\n")
    sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
    blocks, total_d, total_i = [], 0, 0
    for group in sm.get_grouped_opcodes(context):
        chunk_html = []
        first = group[0]
        chunk_html.append(f'<div class="loc">line {first[3] + 1}</div>')
        for tag, i1, i2, j1, j2 in group:
            if tag == "equal":
                for line in b[j1:j2]:
                    if line.strip():
                        chunk_html.append(f'<p dir="auto" class="ctx">{html.escape(line)}</p>')
                continue
            segs = word_diff("\n".join(a[i1:i2]), "\n".join(b[j1:j2]))
            d, n = count_words(segs)
            total_d += d
            total_i += n
            for p in segs_to_paragraphs(segs):
                if p.strip():
                    chunk_html.append(f'<p dir="auto" class="chg">{p}</p>')
        blocks.append('<div class="hunk">' + "".join(chunk_html) + "</div>")
    if not blocks:
        return '<p class="muted">No text changes.</p>', 0, 0
    sep = '<div class="gap">⋯</div>'
    return sep.join(blocks), total_d, total_i


CSS = """
:root{--bg:#fff;--fg:#1f2328;--muted:#6b7280;--card:#f6f8fa;--line:#d0d7de;
--del-bg:#ffe5e5;--del-fg:#b42318;--ins-bg:#dcfce7;--ins-fg:#146c2e;--accent:#2563eb}
@media (prefers-color-scheme:dark){:root{--bg:#0f1115;--fg:#e6e6e6;--muted:#9aa3ae;--card:#171a21;
--line:#2b313b;--del-bg:#4a1d1d;--del-fg:#ffb4ab;--ins-bg:#16341f;--ins-fg:#9be6ad;--accent:#7aa2ff}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);
font:16px/1.75 "Segoe UI","Noto Sans Hebrew",Arial,sans-serif}
main{max-width:960px;margin:0 auto;padding:24px 16px 64px}
h1{font-size:1.5rem;margin:0 0 4px}
.muted{color:var(--muted)}
.legend{margin:8px 0 24px;font-size:.95rem}
del{background:var(--del-bg);color:var(--del-fg);text-decoration:line-through;border-radius:3px;padding:0 1px}
ins{background:var(--ins-bg);color:var(--ins-fg);text-decoration:underline;text-underline-offset:3px;border-radius:3px;padding:0 1px}
table{border-collapse:collapse;width:100%;font-size:.92rem;margin-bottom:28px}
th,td{border-bottom:1px solid var(--line);padding:6px 8px;text-align:start;vertical-align:top}
th{color:var(--muted);font-weight:600}
td.num{white-space:nowrap;font-variant-numeric:tabular-nums}
a{color:var(--accent);text-decoration:none}
details.commit{border:1px solid var(--line);border-radius:10px;margin:14px 0;background:var(--card)}
details.commit>summary{cursor:pointer;padding:10px 14px;list-style-position:inside}
.msg{font-weight:600}
.meta{font-size:.85rem;color:var(--muted)}
.file{background:var(--bg);border-top:1px solid var(--line);padding:10px 14px}
.fname{font-family:Consolas,monospace;font-size:.9rem;margin-bottom:6px}
.tag{font-size:.75rem;padding:1px 6px;border-radius:8px;border:1px solid var(--line);margin-inline-start:6px}
.hunk p{margin:4px 0;white-space:pre-wrap;overflow-wrap:anywhere}
.hunk p.ctx{color:var(--muted)}
.loc{font-size:.75rem;color:var(--muted);font-family:Consolas,monospace}
.gap{text-align:center;color:var(--muted);margin:4px 0}
.count .d{color:var(--del-fg)} .count .i{color:var(--ins-fg)}
"""

LEGEND = ('<div class="legend">Legend: <del>deleted words</del> &nbsp; <ins>inserted words</ins> '
          '&nbsp; <span class="muted">grey = unchanged context</span></div>')


def page(title, body):
    return (f'<!doctype html><html><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1">'
            f"<title>{html.escape(title)}</title><style>{CSS}</style></head>"
            f"<body><main>{body}</main></body></html>")


def count_html(d, i):
    return f'<span class="count"><span class="d">−{d}</span> / <span class="i">+{i}</span> words</span>'


# ---------------------------------------------------------------- output name

def changes_name(path):
    """docs/a.md -> docs/a.changes.html, so one ignore rule (*.changes.html) covers every report."""
    p = Path(path)
    return str(p.with_name(p.stem + ".changes.html"))


def history_output(repo, paths):
    """Name the report after the file when all paths are one file under its old and new
    names (a.qmd + a.md), otherwise after the repository. It goes in the repository."""
    stems = {str(Path(p).with_suffix("")) for p in paths}
    if len(stems) == 1 and not any(ch in p for p in paths for ch in "*?[:"):
        return changes_name(Path(repo) / paths[0])
    return str(Path(repo) / (Path(repo).resolve().name + ".changes.html"))


# ---------------------------------------------------------------- compare mode

def cmd_compare(args):
    old = Path(args.old).read_text(encoding="utf-8")
    new = Path(args.new).read_text(encoding="utf-8")
    body, d, i = render_file_diff(old, new, args.context)
    title = f"{Path(args.old).name} → {Path(args.new).name}"
    out = (f"<h1>{html.escape(title)}</h1><div class='muted'>{count_html(d, i)}</div>{LEGEND}"
           f'<div class="file">{body}</div>')
    output = args.output or changes_name(args.new)
    Path(output).write_text(page(title, out), encoding="utf-8")
    print(f"Wrote {output}  (-{d} / +{i} words)")


# ---------------------------------------------------------------- history mode

def git(repo, *a, binary=False):
    r = subprocess.run(["git", "-C", repo, "-c", "core.quotepath=off", *a],
                       capture_output=True)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.decode("utf-8", "replace").strip())
    return r.stdout if binary else r.stdout.decode("utf-8", "replace")


def show(repo, rev, path):
    try:
        return git(repo, "show", f"{rev}:{path}")
    except RuntimeError:
        return ""


def list_commits(repo, args):
    cmd = ["log", "--format=%H%x1f%P%x1f%an%x1f%aI%x1f%s%x1e"]
    if args.since:
        cmd.append(f"--since={args.since}")
    if not args.oldest_first:
        pass
    else:
        cmd.append("--reverse")
    if args.range:
        cmd.append(args.range)
    cmd += ["--", *args.paths]
    commits = []
    for rec in git(repo, *cmd).split("\x1e"):
        rec = rec.strip("\n")
        if not rec:
            continue
        h, parents, author, date, subject = rec.split("\x1f")
        commits.append(dict(hash=h, parent=(parents.split() or [None])[0],
                            author=author, date=date, subject=subject))
    return commits


def changed_files(repo, c, paths):
    base = ["diff-tree", "-r", "-z", "-M", "--name-status", "--no-commit-id"]
    if c["parent"]:
        out = git(repo, *base, c["parent"], c["hash"], "--", *paths)
    else:
        out = git(repo, *base, "--root", c["hash"], "--", *paths)
    parts = out.split("\0")
    files, k = [], 0
    while k < len(parts) and parts[k]:
        status = parts[k]
        if status[0] in "RC":
            files.append((status[0], parts[k + 1], parts[k + 2]))
            k += 3
        else:
            files.append((status[0], parts[k + 1], parts[k + 1]))
            k += 2
    return files


STATUS = {"A": "added", "D": "deleted", "M": "modified", "R": "renamed", "C": "copied", "T": "type changed"}


def cmd_history(args):
    repo = args.repo
    commits = list_commits(repo, args)
    if not commits:
        sys.exit("No commits touch the selected files.")
    rows, sections = [], []
    total_d = total_i = 0
    for n, c in enumerate(commits, 1):
        file_html, cd, ci = [], 0, 0
        for status, old_path, new_path in changed_files(repo, c, args.paths):
            old = show(repo, c["parent"], old_path) if c["parent"] and status != "A" else ""
            new = show(repo, c["hash"], new_path) if status != "D" else ""
            body, d, i = render_file_diff(old, new, args.context)
            cd += d
            ci += i
            name = html.escape(new_path if old_path == new_path else f"{old_path} → {new_path}")
            file_html.append(f'<div class="file"><div class="fname">{name}'
                             f'<span class="tag">{STATUS.get(status, status)}</span> '
                             f'{count_html(d, i)}</div>{body}</div>')
        total_d += cd
        total_i += ci
        date = datetime.fromisoformat(c["date"]).strftime("%Y-%m-%d %H:%M")
        anchor = f"c{n}"
        subj = html.escape(c["subject"])
        rows.append(f'<tr><td class="num">{date}</td><td dir="auto"><a href="#{anchor}">{subj}</a></td>'
                    f'<td>{html.escape(c["author"])}</td><td class="num">{count_html(cd, ci)}</td></tr>')
        sections.append(
            f'<details class="commit" id="{anchor}" {"open" if args.expand else ""}><summary>'
            f'<span class="msg" dir="auto">{subj}</span><div class="meta">{date} · '
            f'{html.escape(c["author"])} · {c["hash"][:8]} · {count_html(cd, ci)}</div>'
            f'</summary>{"".join(file_html)}</details>')
    repo_name = Path(repo).resolve().name
    title = f"Change report – {repo_name}"
    body = (f"<h1>{html.escape(title)}</h1>"
            f'<div class="muted">{len(commits)} commits · files: {html.escape(" ".join(args.paths))} · '
            f"{count_html(total_d, total_i)} · generated {datetime.now():%Y-%m-%d %H:%M}</div>{LEGEND}"
            f"<table><tr><th>Date</th><th>Change</th><th>Author</th><th>Words</th></tr>{''.join(rows)}</table>"
            f"{''.join(sections)}")
    output = args.output or history_output(repo, args.paths)
    Path(output).write_text(page(title, body), encoding="utf-8")
    print(f"Wrote {output}  ({len(commits)} commits, -{total_d} / +{total_i} words)")


# ---------------------------------------------------------------- CLI

def main():
    ap = argparse.ArgumentParser(description="Word-level redline reports for Markdown files.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("compare", help="compare two files")
    c.add_argument("old")
    c.add_argument("new")
    c.add_argument("-o", "--output", help="default: NEW's name with .changes.html, beside it")
    c.add_argument("--context", type=int, default=1, help="unchanged paragraphs shown around a change")
    c.set_defaults(func=cmd_compare)

    h = sub.add_parser("history", help="report all changes in a Git repo")
    h.add_argument("repo", nargs="?", default=".")
    h.add_argument("-o", "--output",
                   help="default: <file>.changes.html for one file, else <repo>.changes.html, in REPO")
    h.add_argument("--range", help="e.g. v1..HEAD or HEAD~10..HEAD")
    h.add_argument("--since", help='e.g. 2026-09-01 or "2 weeks ago"')
    h.add_argument("--paths", nargs="+", default=["*.md"], help='file patterns (default "*.md")')
    h.add_argument("--context", type=int, default=1, help="unchanged paragraphs shown around a change")
    h.add_argument("--oldest-first", action="store_true")
    h.add_argument("--expand", action="store_true", help="open all commits by default")
    h.set_defaults(func=cmd_history)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
