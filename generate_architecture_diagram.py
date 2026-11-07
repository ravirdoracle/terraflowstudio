#!/usr/bin/env python3
"""
Generate the Terraflow Studio code-architecture (package layering) diagram.

Usage:
    python generate_architecture_diagram.py [output_file.png]

Default output: architecture_layering.png

Companion to generate_odb_aws_diagram.py, which draws the *deployment* topology.
This one draws the *code* structure: the package layering documented in DESIGN.md
and in the architecture .docx, where it is Figure 1.

Drawn with PIL rather than a graph library because the layout is hand-composed:
the point of the picture is the direction of the arrows and the fact that the
three cloud boxes have no edge between them, which an auto-layout engine would
not preserve. Palette is taken from the documentation itself.

Box heights are derived from their content so nothing carries dead space - the
image is placed at a fixed page width, so every wasted pixel of height shrinks
the type.

Requires Pillow. Fonts are the Windows system Arial / Consolas.
"""
import math
import os
import sys
from PIL import Image, ImageDraw, ImageFont

OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
    os.path.dirname(os.path.abspath(__file__)), 'architecture_layering.png')

# ── palette, lifted from the .docx ───────────────────────────────────────────
INK       = (26, 26, 24)         # #1A1A18  body / title text
MUTED     = (74, 74, 71)         # #4A4A47  secondary text
GOLD      = (201, 162, 39)       # #C9A227  accent
GOLD_FILL = (250, 246, 232)
SHADE     = (238, 238, 232)      # #EEEEE8  code-block ground
CODE_INK  = (51, 51, 48)         # #333330
WHITE     = (255, 255, 255)
RULE      = (198, 198, 190)
FORBID    = (176, 58, 46)

S = 3                            # supersample factor, downscaled at the end
W, H = 1870, 980

F = r"C:\Windows\Fonts"
def font(name, size):
    return ImageFont.truetype(os.path.join(F, name), size * S)

f_lbl  = font('arialbd.ttf', 19)
f_sub  = font('consola.ttf', 13)
f_note = font('arial.ttf', 14)
f_red  = font('arialbd.ttf', 14)
f_edge = font('arial.ttf', 13)
f_cap  = font('arialbd.ttf', 17)
f_mono = font('consolab.ttf', 17)

TITLE_Y, LINE_1, STEP, PAD = 16, 38, 19, 8

img = Image.new('RGB', (W * S, H * S), WHITE)
d = ImageDraw.Draw(img)


def box_h(lines):
    """Height that exactly fits `lines` under a title."""
    return (LINE_1 + STEP * len(lines) + PAD) if lines else 54


def box(x, y, w, lines, title, fill=WHITE, border=INK, bw=2, dashed=False):
    h = box_h(lines)
    xy = [x * S, y * S, (x + w) * S, (y + h) * S]
    d.rounded_rectangle(xy, radius=7 * S, fill=fill,
                        outline=None if dashed else border, width=bw * S)
    if dashed:
        _dashed(x, y, w, h, border, bw)
    ty = y + (h / 2 if not lines else TITLE_Y)
    d.text(((x + w / 2) * S, ty * S), title, font=f_lbl, fill=INK, anchor='mm')
    ly = y + LINE_1
    for ln in lines:
        d.text(((x + w / 2) * S, ly * S), ln, font=f_sub, fill=CODE_INK, anchor='mm')
        ly += STEP
    return y + h


def _dashed(x, y, w, h, col, bw, dash=9, gap=6):
    def seg(x0, y0, x1, y1):
        L = math.hypot(x1 - x0, y1 - y0)
        n = max(1, int(L // (dash + gap)))
        for i in range(n + 1):
            a, b = i * (dash + gap) / L, min(1.0, (i * (dash + gap) + dash) / L)
            if a >= 1:
                break
            d.line([(x0 + (x1 - x0) * a) * S, (y0 + (y1 - y0) * a) * S,
                    (x0 + (x1 - x0) * b) * S, (y0 + (y1 - y0) * b) * S],
                   fill=col, width=bw * S)
    seg(x + 7, y, x + w - 7, y); seg(x + 7, y + h, x + w - 7, y + h)
    seg(x, y + 7, x, y + h - 7); seg(x + w, y + 7, x + w, y + h - 7)


def arrow(x0, y0, x1, y1, col=INK, bw=3, head=12):
    d.line([x0 * S, y0 * S, x1 * S, y1 * S], fill=col, width=bw * S)
    ang = math.atan2(y1 - y0, x1 - x0)
    for s in (2.55, -2.55):
        d.line([x1 * S, y1 * S,
                (x1 + head * math.cos(ang + s)) * S,
                (y1 + head * math.sin(ang + s)) * S], fill=col, width=bw * S)


# ══════════════════════════════════════════════════════════════════════════════
d.text((935 * S, 38 * S),
       'Package layering \u2014 the dependency direction is the architecture',
       font=f_cap, fill=INK, anchor='mm')
d.text((935 * S, 64 * S),
       'An arrow means "imports". Every arrow points down, and there is none between the cloud packages \u2014 that absence is the whole design.',
       font=f_note, fill=MUTED, anchor='mm')

LX, LW = 180, 1220                       # main stack: x and width
CX = LX + LW / 2                         # 790

# ── entry ────────────────────────────────────────────────────────────────────
y = box(LX, 94, LW, [],
        'app.py   \u2014   Flask app factory  \u00b7  shared API routes  \u00b7  blueprint registration',
        fill=SHADE, border=MUTED)
arrow(CX, y, CX, 182, col=MUTED, bw=2)

y = box(390, 184, 800, ['generate  \u00b7  zip_name  \u00b7  validate  \u00b7  selftest'],
        'clouds/registry.py   \u2014   one CloudSpec per cloud',
        fill=GOLD_FILL, border=GOLD, bw=3)
d.text((1215 * S, 218 * S), 'every route dispatches',
       font=f_edge, fill=MUTED, anchor='lm')
d.text((1215 * S, 236 * S), 'through this one table',
       font=f_edge, fill=MUTED, anchor='lm')

# ── cloud layer ──────────────────────────────────────────────────────────────
CLOUD_Y, CW = 318, 380
xs = (180, 600, 1020)
rows = ['generator  \u00b7  validator', 'schema  \u00b7  selftest  \u00b7  routes',
        'templates/  \u2192  Terraform', 'pages/      \u2192  HTML']
for x, name in zip(xs, ('clouds/aws', 'clouds/gcp', 'clouds/azure')):
    arrow(CX, y, x + CW / 2, CLOUD_Y - 2, col=GOLD, bw=2)
    cloud_bottom = box(x, CLOUD_Y, CW, rows, name, bw=3)

# the absent edges, marked
for mx in (590, 1010):
    my = CLOUD_Y + box_h(rows) / 2
    for a, b in (((-12, -12), (12, 12)), ((-12, 12), (12, -12))):
        d.line([(mx + a[0]) * S, (my + a[1]) * S, (mx + b[0]) * S, (my + b[1]) * S],
               fill=FORBID, width=3 * S)
d.text((1430 * S, (CLOUD_Y + 44) * S), 'no cross-cloud imports',
       font=f_red, fill=FORBID, anchor='lm')
d.text((1430 * S, (CLOUD_Y + 66) * S), 'enforced by AST in',
       font=f_note, fill=MUTED, anchor='lm')
d.text((1430 * S, (CLOUD_Y + 86) * S), 'test_architecture.py,',
       font=font('consola.ttf', 13), fill=CODE_INK, anchor='lm')
d.text((1430 * S, (CLOUD_Y + 106) * S), 'not by convention',
       font=f_note, fill=MUTED, anchor='lm')

# ── oci ──────────────────────────────────────────────────────────────────────
OCI_Y = 500
for x in xs:
    arrow(x + CW / 2, cloud_bottom, x + CW / 2, OCI_Y - 2, bw=2)
y = box(LX, OCI_Y, LW,
        ['database   \u2192  DB Home \u00b7 CDB \u00b7 PDB        dataguard  \u2192  Multi-AZ (LPG) \u00b7 Cross-Region (DRG/RPC)',
         'templates/ hold only oci_core_* and oci_database_* resources',
         'the supported surface is oci/__all__ \u2014 importing oci.database directly is a test failure'],
        'oci/   \u2014   shared by all three clouds, depends on none of them', bw=3)

# ── core ─────────────────────────────────────────────────────────────────────
CORE_Y = 658
arrow(CX, y, CX, CORE_Y - 2, bw=2)
y = box(LX, CORE_Y, LW,
        ['helpers  \u2192  make_renderer (one Jinja loader per package) \u00b7 tf_bool \u00b7 tf_num \u00b7 parse_list',
         'pages    \u2192  render_page (no-store)          selftest  \u2192  Recorder'],
        'core/   \u2014   knows about no cloud', fill=SHADE, border=MUTED, bw=3)

d.text((CX * S, 778 * S), 'core   \u2190   oci   \u2190   clouds/*   \u2190   clouds/registry.py',
       font=f_mono, fill=INK, anchor='mm')

# ── supporting cast ──────────────────────────────────────────────────────────
d.line([180 * S, 806 * S, 1690 * S, 806 * S], fill=RULE, width=2 * S)
SY = 832
box(180, SY, 480,
    ['<cloud>_regions.json  \u00b7  <cloud>_shapes.json',
     'validated on load AND on save \u00b7 atomic write',
     'injected into the page; read by the generators'],
    'config/   \u2014   catalogues', border=RULE, dashed=True)
box(695, SY, 480,
    ['test_architecture.py  \u2014  53 tests, real AST',
     'fails the moment an arrow above is violated',
     'snapshot {path: sha256} to verify a refactor'],
    'tests/   \u2014   1033 tests', border=RULE, dashed=True)
box(1210, SY, 480,
    ['generate_<cloud>_tf(data) -> {path: content}',
     'zip \u00b7 file tree \u00b7 GitHub push \u00b7 tf_validator',
     'nothing downstream knows which cloud made it'],
    'output   \u2014   one contract', fill=GOLD_FILL, border=GOLD, dashed=True)

img.resize((W, H), Image.LANCZOS).save(OUT, 'PNG', optimize=True)
print(f'✓  Diagram written to:  {OUT}')
print(f'   {os.path.getsize(OUT):,} bytes  ·  place at 6.75 in wide on a Letter page')
