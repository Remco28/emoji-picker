"""Layout numbers shared by the window and the search evaluation.

The eval scores results "as the window shows them", so both must agree on
how many emoji fit on a line at the default window size.
"""
from . import design

CELL = design.cell_width(design.EMOJI_DEFAULT)  # px per emoji cell at the default emoji size


def columns(chart_width=design.chart_width(design.DEFAULT_WIDTH), cell=CELL):
    return max(4, chart_width // cell)


COLUMNS = columns()
