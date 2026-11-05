"""Keyboard movement through the chart, independent of GTK.

The chart is a list of sections; each starts on a new line and wraps every
`columns` cells. The highlight is a flat index in reading order. Up and Down
keep the column where possible and clamp to a shorter line; Left and Right
step through reading order; Page Up/Down move by a number of lines.
"""


class Grid:
    def __init__(self, section_lengths, columns):
        self.columns = max(1, columns)
        self.cells = []  # flat index -> (line, column)
        self.lines = []  # line -> list of flat indexes
        line = 0
        for n in section_lengths:
            for k in range(n):
                ln, col = line + k // self.columns, k % self.columns
                while len(self.lines) <= ln:
                    self.lines.append([])
                self.lines[ln].append(len(self.cells))
                self.cells.append((ln, col))
            line += (n + self.columns - 1) // self.columns
        # drop empty lines left by empty sections (none are created, but be safe)
        self.lines = [ln for ln in self.lines if ln]
        self._line_of = {}
        for ln, idxs in enumerate(self.lines):
            for i in idxs:
                self._line_of[i] = ln

    def __len__(self):
        return len(self.cells)

    def _vertical(self, cur, dl):
        if not self.cells:
            return None
        ln = self._line_of[cur] + dl
        ln = max(0, min(len(self.lines) - 1, ln))
        col = self.cells[cur][1]
        target = self.lines[ln]
        return target[min(col, len(target) - 1)]

    def move(self, cur, key, page_lines=5):
        if not self.cells:
            return None
        if cur is None:
            return 0
        if key == "left":
            return max(0, cur - 1)
        if key == "right":
            return min(len(self.cells) - 1, cur + 1)
        if key == "up":
            return self._vertical(cur, -1)
        if key == "down":
            return self._vertical(cur, +1)
        if key == "page_up":
            return self._vertical(cur, -page_lines)
        if key == "page_down":
            return self._vertical(cur, +page_lines)
        if key == "home":
            return 0
        if key == "end":
            return len(self.cells) - 1
        return cur
