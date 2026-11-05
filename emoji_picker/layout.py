"""Layout numbers shared by the window and the search evaluation.

The eval scores results "as the window shows them", so both must agree on
how many emoji fit on a line at the default window size.
"""
DEFAULT_WIDTH = 760
DEFAULT_HEIGHT = 560
CELL = 52          # px per emoji cell at the default emoji size, incl. spacing
SIDE_PADDING = 24  # px of window padding left + right


def columns(width=DEFAULT_WIDTH, cell=CELL):
    return max(4, (width - SIDE_PADDING) // cell)


COLUMNS = columns()
