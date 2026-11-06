"""The picker's design values, in one place (desktop-polish: one set of values).

Text uses libadwaita's type classes (.heading, .caption, .title-4), never px
sizes, so it follows the system font and the Large Text setting. Colours are
libadwaita's named roles (@accent_bg_color and so on), so the picker follows
the system's light/dark style and accent colour. Only emoji glyphs have px
sizes: they behave like pictures, and Ctrl+plus / Ctrl+minus scale them.
"""
# Spacing on a 4 px grid
S1, S2, S3, S6 = 4, 8, 12, 24

# Corners: the highlighted cell; the card uses libadwaita's .card radius
RADIUS_CELL = 8

# Emoji in the chart. A cell is square: the glyph plus CELL_INSET on each side.
EMOJI_SIZES = (24, 28, 32, 40, 48)
EMOJI_DEFAULT = 32
CELL_INSET = 8

# The side card that previews the highlighted emoji
CARD_WIDTH = 200
CARD_EMOJI = 88       # font size; Noto's glyph draws about 96 px (passport-photo size)
CARD_EMOJI_BOX = 112  # height of the space the glyph sits in

PINNED_HEIGHT = 36    # the category title kept at the top of the chart
FADE = 24             # the fade where the chart continues below the edge

DEFAULT_WIDTH, DEFAULT_HEIGHT = 760, 560
MIN_WIDTH, MIN_HEIGHT = 560, 400

# Colour roles
MUTED = "alpha(@window_fg_color, 0.70)"   # secondary text; about 4.9:1 on the light background
BORDER = "alpha(currentColor, 0.15)"      # libadwaita's own border strength
HIGHLIGHT_FILL = "alpha(@accent_bg_color, 0.15)"

CSS_TEMPLATE = """
.ep-section {{
  min-height: {pinned_text}px;
  padding: {s3}px {inset}px {s1}px {inset}px;
}}
.ep-pinned {{
  background-color: @window_bg_color;
}}
.ep-pinned.ep-scrolled {{
  box-shadow: 0 1px {border};
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
  background-color: {highlight_fill};
  box-shadow: inset 0 0 0 2px @accent_bg_color;
}}
.ep-fade {{
  background-image: linear-gradient(to bottom, alpha(@window_bg_color, 0), @window_bg_color);
}}
.ep-muted {{
  color: {muted};
}}
.ep-card-emoji {{
  font-family: "Noto Color Emoji", emoji;
  font-size: {card_emoji}px;
}}
.ep-hints {{
  padding: {s2}px {s3}px;
}}
"""


def css(emoji_size=EMOJI_DEFAULT):
    return CSS_TEMPLATE.format(s1=S1, s2=S2, s3=S3, inset=CELL_INSET, radius_cell=RADIUS_CELL,
                               emoji=emoji_size, cell=cell_width(emoji_size),
                               pinned_text=PINNED_HEIGHT - S3 - S1, card_emoji=CARD_EMOJI,
                               muted=MUTED, border=BORDER, highlight_fill=HIGHLIGHT_FILL)


def cell_width(emoji_size=EMOJI_DEFAULT):
    return emoji_size + 2 * CELL_INSET


def chart_width(window_width):
    """Width the chart gets in a window this wide: the card, its margins and
    the chart's own margins taken off."""
    return window_width - CARD_WIDTH - 4 * S3
