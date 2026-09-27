"""Render paper/content.py to an IEEE two-column conference PDF and to IEEEtran LaTeX.

    python paper/build_paper.py            # writes paper/main.pdf and paper/main.tex

The PDF uses reportlab (no TeX installation needed): US letter, 0.625 in side margins,
two 3.5 in columns with a 0.25 in gap, 10 pt Times body. Figures float to the top of the
page after their first reference, the way LaTeX places figure* floats. main.tex compiles
with the standard IEEEtran class (e.g. on Overleaf) against the same figure files.
Run the figure scripts first; the figures themselves are not stored in the repository.
"""
import json
import re
import sys
from pathlib import Path

from PIL import Image
from reportlab.lib.colors import HexColor
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import textwrap

import pandas as pd
from reportlab.platypus import (BaseDocTemplate, Flowable, Frame, FrameBreak, KeepTogether, PageBreak,
                                PageTemplate, Paragraph, Preformatted, Spacer, Table, TableStyle)

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
import content as C  # noqa: E402

# ------------------------------------------------------------------ fonts
FONT_DIR = Path("C:/Windows/Fonts")
FACES = {"Times": "times.ttf", "Times-B": "timesbd.ttf", "Times-I": "timesi.ttf", "Times-BI": "timesbi.ttf",
         "Mono": "cour.ttf"}
if all((FONT_DIR / f).exists() for f in FACES.values()):
    for name, f in FACES.items():
        pdfmetrics.registerFont(TTFont(name, str(FONT_DIR / f)))
    pdfmetrics.registerFontFamily("Times", normal="Times", bold="Times-B", italic="Times-I", boldItalic="Times-BI")
    SERIF, MONO = "Times", "Mono"
else:  # built-in Type-1 fallback (Latin-1 only)
    SERIF, MONO = "Times-Roman", "Courier"

# ------------------------------------------------------------------ geometry (points)
PW, PH = letter
LM = RM = 45.0            # 0.625 in
TM, BM = 54.0, 72.0       # 0.75 in, 1 in
TEXT_W = PW - LM - RM     # 522 = two 252 pt columns + 18 pt gap
COL_W, GAP = 252.0, 18.0
TEXT_H = PH - TM - BM
TITLE_H = 128.0

INK = HexColor("#000000")
BODY = ParagraphStyle("body", fontName=SERIF, fontSize=10, leading=11.6, alignment=TA_JUSTIFY,
                      firstLineIndent=10, textColor=INK)
BODY_FIRST = ParagraphStyle("body1", parent=BODY, firstLineIndent=0)
ABSTRACT = ParagraphStyle("abs", fontName="Times-B" if SERIF == "Times" else "Times-Bold", fontSize=9,
                          leading=10.4, alignment=TA_JUSTIFY)
H1 = ParagraphStyle("h1", fontName=SERIF, fontSize=10, leading=12, alignment=TA_CENTER, spaceBefore=8,
                    spaceAfter=4, keepWithNext=1)
H2 = ParagraphStyle("h2", fontName="Times-I" if SERIF == "Times" else "Times-Italic", fontSize=10, leading=12,
                    alignment=TA_LEFT, spaceBefore=5, spaceAfter=2, keepWithNext=1)
CAP = ParagraphStyle("cap", fontName=SERIF, fontSize=8, leading=9.4, alignment=TA_JUSTIFY)
TCAP = ParagraphStyle("tcap", fontName=SERIF, fontSize=8, leading=9.6, alignment=TA_CENTER, keepWithNext=1,
                      spaceAfter=3)
TCELL = ParagraphStyle("tcell", fontName=SERIF, fontSize=7.6, leading=8.8, alignment=TA_LEFT)
TNOTE = ParagraphStyle("tnote", fontName=SERIF, fontSize=7, leading=8.2, alignment=TA_JUSTIFY)
REF = ParagraphStyle("ref", fontName=SERIF, fontSize=8, leading=9.4, leftIndent=16, firstLineIndent=-16,
                     alignment=TA_LEFT, spaceAfter=1.5)
LIST = ParagraphStyle("list", parent=BODY, firstLineIndent=0, leftIndent=12, bulletIndent=2, spaceAfter=1.5)
TITLE = ParagraphStyle("title", fontName=SERIF, fontSize=22, leading=26, alignment=TA_CENTER)
AUTH = ParagraphStyle("auth", fontName=SERIF, fontSize=11, leading=13, alignment=TA_CENTER)
MONO_S = ParagraphStyle("mono", fontName=MONO, fontSize=6.3, leading=7.3)
CODE_S = ParagraphStyle("code", fontName=MONO, fontSize=7.0, leading=8.2)
AFF = ParagraphStyle("aff", fontName="Times-I" if SERIF == "Times" else "Times-Italic", fontSize=9.5,
                     leading=11.5, alignment=TA_CENTER)


def roman(n):
    vals = [(10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I")]
    out = ""
    for v, s in vals:
        while n >= v:
            out, n = out + s, n - v
    return out


# ------------------------------------------------------------------ numbering pre-pass
FIG_NUM, TAB_NUM, CITE_ORDER = {}, {}, []
ALL_BLOCKS = C.BODY + getattr(C, "APPENDIX", [])
for kind, *rest in ALL_BLOCKS:
    if kind == "fig":
        FIG_NUM[rest[0]] = len(FIG_NUM) + 1
    elif kind == "table":
        TAB_NUM[rest[0]] = len(TAB_NUM) + 1


def _scan_cites(text):
    for m in re.finditer(r"\{c:([^}]+)\}", text):
        for k in m.group(1).split(","):
            k = k.strip()
            if k not in C.REFS:
                raise KeyError(f"unknown reference {k}")
            if k not in CITE_ORDER:
                CITE_ORDER.append(k)


_scan_cites(C.ABSTRACT)
for kind, *rest in ALL_BLOCKS:
    for part in rest:
        for t in (part if isinstance(part, list) else [part]):
            if isinstance(t, str):
                _scan_cites(t)
for k in C.FIGS:
    _scan_cites(C.FIGS[k][2])
CITE_NUM = {k: i + 1 for i, k in enumerate(CITE_ORDER)}

def smart_quotes(text):
    """Straight quotes -> typographic quotes, leaving `code` spans untouched."""
    out, open_dq = [], True
    for i, seg in enumerate(re.split(r"(`[^`]+`)", text)):
        if i % 2:
            out.append(seg)
            continue
        buf = []
        for j, ch in enumerate(seg):
            if ch == '"':
                buf.append("“" if open_dq else "”")
                open_dq = not open_dq
            elif ch == "'":
                prev = seg[j - 1] if j else " "
                buf.append("‘" if prev in " (“" else "’")
            else:
                buf.append(ch)
        out.append("".join(buf))
    return "".join(out)


TOKEN = re.compile(r"(\*\*.+?\*\*|\*[^*]+?\*|`[^`]+`|\{c:[^}]+\}|\{fig:[^}]+\}|\{tab:[^}]+\}|\{sup:[^}]+\}|\{sub:[^}]+\})")


# ------------------------------------------------------------------ markup -> reportlab
def _esc_rl(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def rl(text, _top=True):
    if _top:
        text = smart_quotes(text)
    out = []
    for tok in TOKEN.split(text):
        if not tok:
            continue
        if tok.startswith("**") and tok.endswith("**"):
            out.append(f"<b>{rl(tok[2:-2], False)}</b>")
        elif tok.startswith("`"):
            out.append(f'<font name="{MONO}" size="8.6">{_esc_rl(tok[1:-1])}</font>')
        elif tok.startswith("*") and tok.endswith("*") and len(tok) > 2:
            out.append(f"<i>{rl(tok[1:-1], False)}</i>")
        elif tok.startswith("{c:"):
            out.append(", ".join(f"[{CITE_NUM[k.strip()]}]" for k in tok[3:-1].split(",")))
        elif tok.startswith("{fig:"):
            out.append(f"Fig. {FIG_NUM[tok[5:-1]]}")
        elif tok.startswith("{tab:"):
            out.append(f"Table {roman(TAB_NUM[tok[5:-1]])}")
        elif tok.startswith("{sup:"):
            out.append(f"<super>{_esc_rl(tok[5:-1])}</super>")
        elif tok.startswith("{sub:"):
            out.append(f"<sub>{_esc_rl(tok[5:-1])}</sub>")
        else:
            out.append(_esc_rl(tok))
    return "".join(out)


def smallcaps(text, size=10):
    """IEEE section style: upper-case, with non-initial letters one step smaller."""
    words = []
    for w in text.split(" "):
        if not w:
            continue
        words.append(f'{_esc_rl(w[0].upper())}<font size="{size * 0.8:.1f}">{_esc_rl(w[1:].upper())}</font>')
    return " ".join(words)


# ------------------------------------------------------------------ markup -> LaTeX
TEX_CHARS = {"\\": r"\textbackslash{}", "&": r"\&", "%": r"\%", "$": r"\$", "#": r"\#", "_": r"\_",
             "{": r"\{", "}": r"\}", "~": r"\textasciitilde{}", "^": r"\textasciicircum{}",
             "<": r"\textless{}", ">": r"\textgreater{}"}
TEX_UNI = {"–": "--", "—": "---", "×": r"$\times$", "ρ": r"$\rho$", "≥": r"$\geq$", "≤": r"$\leq$",
           "→": r"$\rightarrow$", "“": "``", "”": "''", "’": "'", "‘": "`", "…": r"\ldots{}",
           "≈": r"$\approx$", "±": r"$\pm$", "−": r"$-$", "·": r"$\cdot$"}


def _esc_tex(s):
    s = "".join(TEX_CHARS.get(ch, ch) for ch in s)
    for a, b in TEX_UNI.items():
        s = s.replace(a, b)
    # straight double quotes -> TeX quotes, alternating open/close
    parts = s.split('"')
    return "".join(p + (("``" if i % 2 == 0 else "''") if i < len(parts) - 1 else "") for i, p in enumerate(parts))


def tex(text, _top=True):
    if _top:
        text = smart_quotes(text)
    out = []
    for tok in TOKEN.split(text):
        if not tok:
            continue
        if tok.startswith("**") and tok.endswith("**"):
            out.append(r"\textbf{" + tex(tok[2:-2], False) + "}")
        elif tok.startswith("`"):
            out.append(r"\texttt{" + _esc_tex(tok[1:-1]) + "}")
        elif tok.startswith("*") and tok.endswith("*") and len(tok) > 2:
            out.append(r"\emph{" + tex(tok[1:-1], False) + "}")
        elif tok.startswith("{c:"):
            out.append(r"\cite{" + ",".join(k.strip() for k in tok[3:-1].split(",")) + "}")
        elif tok.startswith("{fig:"):
            out.append(r"Fig.~\ref{fig:" + tok[5:-1] + "}")
        elif tok.startswith("{tab:"):
            out.append(r"Table~\ref{tab:" + tok[5:-1] + "}")
        elif tok.startswith("{sup:"):
            out.append(r"\textsuperscript{" + _esc_tex(tok[5:-1]) + "}")
        elif tok.startswith("{sub:"):
            out.append(r"\textsubscript{" + _esc_tex(tok[5:-1]) + "}")
        else:
            out.append(_esc_tex(tok))
    return "".join(out)


# ------------------------------------------------------------------ dynamic table: scorecard
def scorecard_table():
    res = json.loads((ROOT / "figures/rerun/scorecard.json").read_text(encoding="utf-8"))
    rows = []
    for t in res["table"]:
        lo, hi = t["ci"]["overall"]
        rows.append([str(t["rank"]), t["model"], f"{t['overall']:.0f} ({lo:.0f}–{hi:.0f})",
                     f"{t['detection']:.0f}", f"{t['escalation']:.0f}", f"{t['uptake']:.0f}",
                     f"{100 * t['p_first']:.0f}%" if t["p_first"] >= 0.005 else "–"])
    note = ("S: overall (95% interval). D: reality detection; E: escalation; U: instruction uptake; all 0–100. "
            "Boundary hold is 100 for every model. P1: probability of ranking first (paired story bootstrap, "
            f"{res['draws']} resamples). Did not finish: " + "; ".join(f"{d['model']} ({d['valid']}/96)" for d in res["dnf"]) + ".")
    return ("Scorecard of the Kaggle Rerun", ["#", "Model", "S", "D", "E", "U", "P1"], rows,
            [0.06, 0.37, 0.22, 0.08, 0.08, 0.08, 0.11], note)


TABLES = dict(C.TABLES)
TABLES["scorecard"] = scorecard_table()


def table_parts(key):
    t = TABLES[key]
    cap, head, rows, widths = t[:4]
    note = t[4] if len(t) > 4 else None
    return cap, head, rows, widths, note


# ------------------------------------------------------------------ figures (floats)
def fig_geom(key):
    path, frac, cap = C.FIGS[key]
    w_px, h_px = Image.open(ROOT / path).size
    w = TEXT_W * frac
    h = w * h_px / w_px
    p = Paragraph(f"<b>Fig. {FIG_NUM[key]}.</b> {rl(cap)}", CAP)
    _, ch = p.wrap(TEXT_W, 400)
    return ROOT / path, w, h, p, ch


class FloatQueue(Flowable):
    """Zero-size marker: when the flow reaches it, queue a figure for the top of the next page."""

    def __init__(self, doc, key):
        super().__init__()
        self.doc, self.key = doc, key
        self.width = self.height = 0

    def draw(self):
        if self.key not in self.doc.queued:
            self.doc.queued.append(self.key)
            self.doc.fig_queue.append(self.key)


class IEEEDoc(BaseDocTemplate):
    def __init__(self, path, **kw):
        super().__init__(str(path), pagesize=letter, leftMargin=LM, rightMargin=RM, topMargin=TM,
                         bottomMargin=BM, title=C.TITLE, author=", ".join(a[0] for a in C.AUTHORS),
                         subject="IEEE-style preprint", **kw)
        self.fig_queue, self.queued, self.drawn = [], [], []
        col = lambda x, h: Frame(x, BM, COL_W, h, leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
        first = [Frame(LM, PH - TM - TITLE_H, TEXT_W, TITLE_H, leftPadding=0, rightPadding=0, topPadding=0,
                       bottomPadding=0), col(LM, TEXT_H - TITLE_H - 6), col(LM + COL_W + GAP, TEXT_H - TITLE_H - 6)]
        templates = [PageTemplate("first", first, onPage=self._foot),
                     PageTemplate("body", [col(LM, TEXT_H), col(LM + COL_W + GAP, TEXT_H)], onPage=self._foot)]
        self.geom = {}
        order = list(FIG_NUM)
        for key in order:
            path, w, h, cap, ch = fig_geom(key)
            self.geom[key] = (path, w, h, cap, ch, h + 5 + ch + 14)
        self.pairs = set()
        for key in order:
            used = self.geom[key][5]
            templates.append(PageTemplate(f"fig_{key}", [col(LM, TEXT_H - used), col(LM + COL_W + GAP, TEXT_H - used)],
                                          onPage=self._make_onpage([key])))
        for a, b in zip(order, order[1:]):  # two consecutive floats may share a page top
            used = self.geom[a][5] + self.geom[b][5]
            if used <= 0.78 * TEXT_H:
                self.pairs.add((a, b))
                templates.append(PageTemplate(f"fig_{a}+{b}", [col(LM, TEXT_H - used), col(LM + COL_W + GAP, TEXT_H - used)],
                                              onPage=self._make_onpage([a, b])))
        self.addPageTemplates(templates)

    def _foot(self, canv, doc):
        canv.saveState()
        canv.setFont(SERIF, 8)
        canv.drawCentredString(PW / 2, BM - 30, str(doc.page))
        canv.restoreState()

    def _make_onpage(self, keys):
        def on_page(canv, doc):
            top = PH - TM
            for key in keys:
                path, w, h, cap, ch, used = self.geom[key]
                canv.drawImage(str(path), LM + (TEXT_W - w) / 2, top - h, width=w, height=h,
                               preserveAspectRatio=True, mask="auto")
                cap.drawOn(canv, LM, top - h - 5 - ch)
                self.drawn.append(key)
                top -= used
            self._foot(canv, doc)
        return on_page

    def handle_pageEnd(self):
        q = self.fig_queue
        if len(q) >= 2 and (q[0], q[1]) in self.pairs:
            name = f"fig_{q.pop(0)}+{q.pop(0)}"
        elif q:
            name = f"fig_{q.pop(0)}"
        else:
            name = "body"
        self.handle_nextPageTemplate(name)
        super().handle_pageEnd()


def build_story(doc):
    story = [Paragraph(rl(C.TITLE), TITLE), Spacer(1, 12)]
    for name, aff, contact in C.AUTHORS:
        story += [Paragraph(rl(name), AUTH), Paragraph(rl(aff), AFF), Paragraph(rl(contact), AFF)]
    story.append(FrameBreak())
    story.append(Paragraph(f"<b><i>Abstract</i></b>—{rl(C.ABSTRACT)}", ABSTRACT))
    story.append(Spacer(1, 5))
    story.append(Paragraph(f"<b><i>Index Terms</i></b>—{rl(C.INDEX_TERMS)}", ABSTRACT))
    story.append(Spacer(1, 4))
    sec = sub = app = 0
    after_heading = True
    for kind, *rest in ALL_BLOCKS:
        if kind in ("h1", "h1*"):
            sub = 0
            if kind == "h1":
                sec += 1
                label = f"{roman(sec)}. {smallcaps(rest[0])}"
            else:
                label = smallcaps(rest[0])
            story.append(Paragraph(label, H1))
            after_heading = True
        elif kind == "app":
            sub = 0
            story.append(Paragraph(f"{smallcaps('Appendix')} {chr(65 + app)}<br/>{smallcaps(rest[0])}", H1))
            app += 1
            after_heading = True
        elif kind == "transcript":
            story.append(Preformatted(transcript_text(rest[0]), MONO_S))
            story.append(Spacer(1, 4))
        elif kind == "code":
            story.append(Preformatted(rest[0], CODE_S))
            story.append(Spacer(1, 4))
            after_heading = True
        elif kind == "h2":
            sub += 1
            story.append(Paragraph(f"{chr(64 + sub)}. {rl(rest[0])}", H2))
            after_heading = True
        elif kind == "p":
            story.append(Paragraph(rl(rest[0]), BODY_FIRST if after_heading else BODY))
            after_heading = False
        elif kind == "list":
            for item in rest[0]:
                story.append(Paragraph(rl(item), LIST, bulletText="•"))
            after_heading = False
        elif kind == "eq":
            eq = Table([[Paragraph(f"<i>{_esc_rl(rest[0])}</i>", ParagraphStyle("eq", parent=BODY, alignment=TA_CENTER,
                                                                                   firstLineIndent=0)), "(1)"]],
                       colWidths=[COL_W - 30, 30])
            eq.setStyle(TableStyle([("FONT", (1, 0), (1, 0), SERIF, 10), ("ALIGN", (1, 0), (1, 0), "RIGHT"),
                                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                                    ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
            story += [Spacer(1, 3), eq, Spacer(1, 3)]
            after_heading = True
        elif kind == "fig":
            story.append(FloatQueue(doc, rest[0]))
        elif kind == "table":
            story += rl_table(rest[0])
    story.append(Paragraph(smallcaps("References"), H1))
    for k in CITE_ORDER:
        story.append(Paragraph(f"[{CITE_NUM[k]}]&nbsp;&nbsp;{_esc_rl(smart_quotes(C.REFS[k]))}", REF))
    return story


def transcript_text(row_id, width=64):
    s = pd.read_csv(ROOT / "data/scenarios.csv")
    t = s.loc[s.row_id == row_id, "transcript"].iloc[0]
    out = []
    for line in t.splitlines():
        out += textwrap.wrap(line, width, subsequent_indent="  ") or [""]
    return "\n".join(out)


def rl_table(key):
    cap, head, rows, widths, note = table_parts(key)
    n = TAB_NUM[key]
    ncol = len(head)
    caption = Paragraph(f"TABLE {roman(n)}<br/>{smallcaps(cap, 8)}", TCAP)
    cell = lambda c, bold=False: Paragraph(("<b>%s</b>" if bold else "%s") % _esc_rl(smart_quotes(c)), TCELL)
    data = [[caption] + [""] * (ncol - 1), [cell(h, True) for h in head]]
    data += [[cell(c) for c in r] for r in rows]
    t = Table(data, colWidths=[COL_W * w for w in widths], repeatRows=2)
    t.setStyle(TableStyle([
        ("SPAN", (0, 0), (-1, 0)), ("BOTTOMPADDING", (0, 0), (-1, 0), 4),
        ("LINEABOVE", (0, 1), (-1, 1), 0.9, INK), ("LINEBELOW", (0, 1), (-1, 1), 0.5, INK),
        ("LINEBELOW", (0, -1), (-1, -1), 0.9, INK), ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 2), ("RIGHTPADDING", (0, 0), (-1, -1), 2),
        ("TOPPADDING", (0, 1), (-1, -1), 1.4), ("BOTTOMPADDING", (0, 1), (-1, -1), 1.4)]))
    parts = [Spacer(1, 4), t]  # caption travels inside the table, so it can split across columns
    if note:
        parts += [Spacer(1, 2), Paragraph(_esc_rl(smart_quotes(note)), TNOTE)]
    parts.append(Spacer(1, 6))
    return parts


def build_pdf(out):
    extra = 0
    while True:
        doc = IEEEDoc(out)
        story = build_story(doc)
        story += [PageBreak()] * extra  # flush floats still queued at the end, if any
        doc.build(story)
        missing = [k for k in FIG_NUM if k not in doc.drawn]
        print(f"pass: {doc.page} pages, unplaced figures: {missing}")
        if not missing:
            return doc.page
        extra += len(missing)
        if extra > 8:
            raise RuntimeError(f"figures never placed: {missing}")


# ------------------------------------------------------------------ LaTeX export
def build_tex(out):
    L = [r"\documentclass[conference]{IEEEtran}",
         r"\usepackage[utf8]{inputenc}", r"\usepackage[T1]{fontenc}", r"\usepackage{graphicx}",
         r"\usepackage{booktabs}", r"\usepackage{amsmath}", r"\usepackage{url}",
         r"\usepackage[hidelinks]{hyperref}", r"\graphicspath{{../}}", "",
         r"\begin{document}", r"\title{" + tex(C.TITLE) + "}", r"\author{"]
    for name, aff, contact in C.AUTHORS:
        L.append(r"\IEEEauthorblockN{" + tex(name) + r"}\IEEEauthorblockA{\textit{" + tex(aff) + r"}\\" + tex(contact) + "}")
    L += ["}", r"\maketitle", r"\begin{abstract}", tex(C.ABSTRACT), r"\end{abstract}",
          r"\begin{IEEEkeywords}", tex(C.INDEX_TERMS), r"\end{IEEEkeywords}", ""]
    in_app = False
    for kind, *rest in ALL_BLOCKS:
        if kind == "app":
            if not in_app:
                L.append(r"\appendices")
                in_app = True
            L.append(r"\section{" + tex(rest[0]) + "}")
        elif kind in ("transcript", "code"):
            body = transcript_text(rest[0]) if kind == "transcript" else rest[0]
            L += [r"{\scriptsize", r"\begin{verbatim}", body, r"\end{verbatim}", "}", ""]
        elif kind == "h1":
            L.append(r"\section{" + tex(rest[0]) + "}")
        elif kind == "h1*":
            L.append(r"\section*{" + tex(rest[0]) + "}")
        elif kind == "h2":
            L.append(r"\subsection{" + tex(rest[0]) + "}")
        elif kind == "p":
            L += [tex(rest[0]), ""]
        elif kind == "list":
            L.append(r"\begin{itemize}")
            L += [r"\item " + tex(i) for i in rest[0]]
            L += [r"\end{itemize}", ""]
        elif kind == "eq":
            L += [r"\begin{equation}", rest[1], r"\end{equation}", ""]
        elif kind == "fig":
            path, frac, cap = C.FIGS[rest[0]]
            L += [r"\begin{figure*}[t]", r"\centering",
                  r"\includegraphics[width=" + f"{frac:.2f}" + r"\textwidth]{" + path + "}",
                  r"\caption{" + tex(cap) + "}", r"\label{fig:" + rest[0] + "}", r"\end{figure*}", ""]
        elif kind == "table":
            cap, head, rows, widths, note = table_parts(rest[0])
            spec = "".join(f"p{{{w * 0.95:.2f}\\columnwidth}}" for w in widths)
            L += [r"\begin{table}[t]", r"\caption{" + tex(cap) + "}", r"\label{tab:" + rest[0] + "}",
                  r"\centering\footnotesize", r"\begin{tabular}{" + spec + "}", r"\toprule",
                  " & ".join(r"\textbf{" + _esc_tex(h) + "}" for h in head) + r" \\", r"\midrule"]
            L += [" & ".join(_esc_tex(c) for c in r) + r" \\" for r in rows]
            L += [r"\bottomrule", r"\end{tabular}"]
            if note:
                L += [r"\par\vspace{2pt}\parbox{\columnwidth}{\scriptsize " + _esc_tex(note) + "}"]
            L += [r"\end{table}", ""]
    L += [r"\begin{thebibliography}{99}"]
    for k in CITE_ORDER:
        ref = _esc_tex(smart_quotes(C.REFS[k]))
        ref = re.sub(r"Available: (\S+)", lambda m: "Available: \\url{" + m.group(1).replace("\\_", "_") + "}", ref)
        L.append(r"\bibitem{" + k + "} " + ref)
    L += [r"\end{thebibliography}", r"\end{document}", ""]
    Path(out).write_text("\n".join(L), encoding="utf-8")


if __name__ == "__main__":
    pages = build_pdf(HERE / "main.pdf")
    build_tex(HERE / "main.tex")
    print(f"wrote paper/main.pdf ({pages} pages) and paper/main.tex; "
          f"{len(FIG_NUM)} figures, {len(TAB_NUM)} tables, {len(CITE_ORDER)} references")
