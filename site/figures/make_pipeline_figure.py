#!/usr/bin/env python3
"""Generate the AIMdb mining-pipeline figure (SVG + PNG) for the paper.

Run: python3 site/figures/make_pipeline_figure.py
Outputs: site/figures/pipeline.svg, site/figures/pipeline.png
"""
from pathlib import Path
import cairosvg

HERE = Path(__file__).resolve().parent

W, H = 1700, 1150
FONT = "Helvetica, Arial, sans-serif"


def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


class Box:
    def __init__(self, cx, cy, w, h):
        self.cx, self.cy, self.w, self.h = cx, cy, w, h

    @property
    def left(self): return self.cx - self.w / 2
    @property
    def right(self): return self.cx + self.w / 2
    @property
    def top(self): return self.cy - self.h / 2
    @property
    def bottom(self): return self.cy + self.h / 2

    def edge_point(self, other):
        """Point on this box's border pointing toward `other`'s center."""
        dx, dy = other.cx - self.cx, other.cy - self.cy
        if dx == 0 and dy == 0:
            return (self.cx, self.cy)
        sx = (self.w / 2) / abs(dx) if dx != 0 else float("inf")
        sy = (self.h / 2) / abs(dy) if dy != 0 else float("inf")
        s = min(sx, sy)
        return (self.cx + dx * s, self.cy + dy * s)


def box_svg(b, lines, fill, stroke, text_color="#1a1d24", rx=12,
            font_size=15.5, bold_first=False, stroke_width=1.6, dash=None):
    dash_attr = f' stroke-dasharray="{dash}"' if dash else ""
    s = (f'<rect x="{b.left:.1f}" y="{b.top:.1f}" width="{b.w}" height="{b.h}" rx="{rx}" '
         f'fill="{fill}" stroke="{stroke}" stroke-width="{stroke_width}"{dash_attr}/>\n')
    n = len(lines)
    line_h = font_size + 6
    start_y = b.cy - (n - 1) * line_h / 2 + font_size / 3
    for i, line in enumerate(lines):
        weight = "700" if (bold_first and i == 0) else "400"
        fs = font_size + (1 if (bold_first and i == 0) else 0)
        s += (f'<text x="{b.cx}" y="{start_y + i*line_h:.1f}" text-anchor="middle" '
              f'font-family="{FONT}" font-size="{fs}" font-weight="{weight}" '
              f'fill="{text_color}">{esc(line)}</text>\n')
    return s


def edge(b1, b2, label=None, dashed=False, color="#5b6472", label_side="above",
         marker="url(#arrow)", pad=0):
    x1, y1 = b1.edge_point(b2)
    x2, y2 = b2.edge_point(b1)
    # pull the arrow tip back slightly so it doesn't touch the box border
    import math
    dx, dy = x2 - x1, y2 - y1
    dist = math.hypot(dx, dy) or 1
    x2 -= dx / dist * pad
    y2 -= dy / dist * pad
    dash_attr = ' stroke-dasharray="6,5"' if dashed else ""
    s = (f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" '
         f'stroke="{color}" stroke-width="1.8"{dash_attr} marker-end="{marker}"/>\n')
    if label:
        mx, my = (x1 + x2) / 2, (y1 + y2) / 2
        offset = -10 if label_side == "above" else 16
        # perpendicular-ish nudge: if the line is mostly horizontal, offset vertically;
        # if mostly vertical, offset horizontally.
        if abs(dx) >= abs(dy):
            ly = my + offset
            lx = mx
        else:
            lx = mx + (18 if label_side == "right" else -18)
            ly = my
        s += (f'<text x="{lx:.1f}" y="{ly:.1f}" text-anchor="middle" '
              f'font-family="{FONT}" font-size="12.5" font-style="italic" '
              f'fill="{color}">{esc(label)}</text>\n')
    return s


# ---- colors ----
BLUE_FILL, BLUE_STROKE = "#e8f0fe", "#3f68b5"
AMBER_FILL, AMBER_STROKE = "#fff2d9", "#c9861a"
TEAL_FILL, TEAL_STROKE = "#e2f5f2", "#0d9488"
RED_FILL, RED_STROKE = "#fdeaea", "#b3504f"
PURPLE_FILL, PURPLE_STROKE = "#f2e9fb", "#7c3aed"
GRAY_FILL, GRAY_STROKE = "#eef0f4", "#5b6472"
LOG_FILL, LOG_STROKE = "#f7f7f9", "#9aa1ad"

# ---- nodes ----
A1 = Box(520, 80, 300, 100)
A2 = Box(1120, 80, 300, 100)
B = Box(820, 235, 420, 90)
C = Box(820, 365, 340, 80)
CONTRIB = Box(300, 545, 280, 130)
D = Box(820, 545, 440, 150)
E = Box(1400, 480, 260, 100)
F = Box(1400, 660, 260, 110)
G = Box(820, 740, 420, 120)
I = Box(820, 895, 420, 90)
L = Box(820, 1015, 420, 80)
LOG = Box(1400, 870, 280, 160)

svg = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">',
       f'<rect x="0" y="0" width="{W}" height="{H}" fill="#ffffff"/>',
       '''<defs>
  <marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
    <path d="M 0 0 L 10 5 L 0 10 z" fill="#5b6472"/>
  </marker>
  <marker id="arrow-gray" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
    <path d="M 0 0 L 10 5 L 0 10 z" fill="#9aa1ad"/>
  </marker>
  <marker id="arrow-purple" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
    <path d="M 0 0 L 10 5 L 0 10 z" fill="#7c3aed"/>
  </marker>
</defs>''']

# audit log panel drawn first (background layer)
svg.append(box_svg(LOG,
    ["Audit log", "extractions.csv", "",
     "append-only: timestamp, paper", "key, DOI, action, result,",
     "reasoning — every transition,", "including rejections"],
    LOG_FILL, LOG_STROKE, text_color="#5b6472", rx=14, font_size=13.5,
    bold_first=True, stroke_width=1.4, dash="5,4"))

svg.append(box_svg(A1, ["OpenAlex API search", "open-access filtered,", "rotating query set"],
                    BLUE_FILL, BLUE_STROKE, bold_first=True))
svg.append(box_svg(A2, ["Hand-supplied PDFs", "user-provided (e.g. papers", "behind institutional access)"],
                    BLUE_FILL, BLUE_STROKE, bold_first=True))
svg.append(box_svg(B, ["Candidate index + OA fetch", "papers_index.csv"], BLUE_FILL, BLUE_STROKE, bold_first=True))
svg.append(edge(A1, B))
svg.append(edge(A2, B))

svg.append(box_svg(C, ["PDF → plain-text extraction"], BLUE_FILL, BLUE_STROKE, bold_first=True))
svg.append(edge(B, C))

svg.append(box_svg(CONTRIB, ["Community contributions", "website form → contributions.csv",
                        "review_status = pending"], PURPLE_FILL, PURPLE_STROKE, bold_first=True))

svg.append(box_svg(D, ["LLM read & scope judgment", "usable multireference calc (CASSCF /",
                        "RASSCF / CASPT2 / NEVPT2 / MRCI) on a", "named compound, active space stated?"],
                    AMBER_FILL, AMBER_STROKE, bold_first=True))
svg.append(edge(C, D))
svg.append(edge(CONTRIB, D, label="reviewed identically", dashed=True, color=PURPLE_STROKE,
                marker="url(#arrow-purple)", label_side="above"))

svg.append(box_svg(E, ["Rejected", "not_usable / text_unreadable", "(logged, no row added)"],
                    RED_FILL, RED_STROKE, bold_first=True))
svg.append(edge(D, E, label="no", label_side="above"))

svg.append(box_svg(F, ["Fetch & extract SI", "figshare / PMC OA packages,", "then re-judge with SI in hand"],
                    BLUE_FILL, BLUE_STROKE, bold_first=True))
svg.append(edge(D, F, label="SI needed", label_side="above"))

svg.append(box_svg(G, ["Row extraction", "copy-never-infer · structure &",
                        "entry-type provenance tagging"], TEAL_FILL, TEAL_STROKE, bold_first=True))
svg.append(edge(D, G, label="yes", label_side="left"))
svg.append(edge(F, G, label="merged back", label_side="above"))

svg.append(edge(D, LOG, dashed=True, color="#9aa1ad", marker="url(#arrow-gray)"))
svg.append(edge(G, LOG, dashed=True, color="#9aa1ad", marker="url(#arrow-gray)"))

svg.append(box_svg(I, ["aimdb.csv", "1,329 rows · 780 papers (append-only)"],
                    GRAY_FILL, GRAY_STROKE, bold_first=True))
svg.append(edge(G, I))

svg.append(box_svg(L, ["Public website", "data.js / index.html"], GRAY_FILL, GRAY_STROKE, bold_first=True))
svg.append(edge(I, L, label="build_site.py", label_side="above"))

svg.append('</svg>')

svg_text = "\n".join(svg)
(HERE / "pipeline.svg").write_text(svg_text, encoding="utf-8")
cairosvg.svg2png(bytestring=svg_text.encode("utf-8"), write_to=str(HERE / "pipeline.png"),
                  scale=2.0, background_color="white")
print("wrote", HERE / "pipeline.svg", "and", HERE / "pipeline.png")
