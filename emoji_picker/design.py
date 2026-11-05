"""The picker's design values, in one place (desktop-polish: one set of values).

Colours come from libadwaita's named roles (@accent_bg_color and so on), so
the picker follows the system's light/dark style and accent colour.
"""
# Text sizes (px)
CAPTION = 11   # section labels, key hints
BODY = 13      # the status line
TITLE = 18     # the search text

# Spacing on a 4 px grid
S1, S2, S3, S4, S6 = 4, 8, 12, 16, 24

# Corners
RADIUS_CELL = 8
RADIUS_FIELD = 8

# Emoji sizes for Ctrl+plus / Ctrl+minus; the cell is the glyph plus padding
EMOJI_SIZES = (24, 28, 32, 40, 48)
EMOJI_DEFAULT = 32
CELL_PADDING = 20  # glyph + this = cell width; 32 + 20 = 52 = layout.CELL

MIN_WIDTH, MIN_HEIGHT = 420, 320

CSS_TEMPLATE = """
window.emoji-picker {{ }}
.ep-search {{
  font-size: {title}px;
  min-height: 40px;
  border-radius: {radius_field}px;
}}
.ep-section {{
  font-size: {caption}px;
  font-weight: 600;
  color: alpha(@window_fg_color, 0.65);
  margin: {s3}px {s1}px {s1}px {s1}px;
}}
.ep-chart flowboxchild {{
  padding: 0;
  border-radius: {radius_cell}px;
}}
.ep-cell {{
  font-family: "Noto Color Emoji", emoji;
  font-size: {emoji}px;
  min-width: {cell}px;
  min-height: {cell}px;
}}
.ep-chart flowboxchild.ep-highlight {{
  background-color: alpha(@accent_bg_color, 0.30);
  box-shadow: inset 0 0 0 2px @accent_bg_color;
}}
.ep-chart flowboxchild:hover {{
  background-color: alpha(@window_fg_color, 0.08);
}}
.ep-status {{
  font-size: {body}px;
  padding: {s2}px {s3}px;
  border-top: 1px solid alpha(@window_fg_color, 0.12);
}}
.ep-hint {{
  font-size: {caption}px;
  color: alpha(@window_fg_color, 0.60);
}}
.ep-empty {{
  font-size: {body}px;
  color: alpha(@window_fg_color, 0.60);
  margin: {s6}px;
}}
"""


def css(emoji_size=EMOJI_DEFAULT):
    return CSS_TEMPLATE.format(title=TITLE, caption=CAPTION, body=BODY, s1=S1, s2=S2, s3=S3,
                               s6=S6, radius_cell=RADIUS_CELL, radius_field=RADIUS_FIELD,
                               emoji=emoji_size, cell=emoji_size + CELL_PADDING - 2 * S1)


def cell_width(emoji_size=EMOJI_DEFAULT):
    return emoji_size + CELL_PADDING
