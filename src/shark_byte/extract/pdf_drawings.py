"""Vector drawings on a PDF page: flowcharts and plotted charts.

A drawing is found by joining the page's drawn shapes, lines, and curves
that touch one another into clusters. A cluster is a flowchart when three
or more of its shapes hold text without enclosing another such shape, and
three or more of its pieces are connectors or arrowheads. A frame drawn
around a slide encloses the shapes on it, so it is not a step. Its words
become the drawing's text, read one shape at a time, top to bottom. Drawn
parts set close beside a flowchart and holding words join it. A cluster is a chart when it has many
pieces, several of them axis ticks, and the words on it are mostly short
labels such as numbers and units. A chart keeps no text of its own; its
caption is attached by the page walk. Shapes inside a table or an embedded
picture, and rules that span most of the page, are not part of any drawing.
"""

from typing import NamedTuple

_MIN_SHAPE_WIDTH = 20.0
_MIN_SHAPE_HEIGHT = 10.0
_MIN_DIAGRAM_SHAPES = 3
_MIN_DIAGRAM_LINKS = 3
_MIN_CHART_PIECES = 12
_MIN_CHART_TICKS = 6
_MIN_CHART_WIDTH = 60.0
_MIN_CHART_HEIGHT = 40.0
_SHORT_LABEL_SHARE = 0.7
_SHORT_LABEL = 6
_TICK = 4.0
_ARROW_MIN = 3.0
_ARROW_MAX = 10.0
_THIN = 2.0
_SHAPE_SLACK = 3.0
_LABEL_REACH = 12.0
_NEIGHBOUR_GAP = 40.0
_PAGE_SPAN = 0.8
_MAX_DRAWN_OBJECTS = 4000

Box = tuple[float, float, float, float]


class Drawing(NamedTuple):
    box: Box
    kind: str
    text: str


def find_drawings(page, words: list[dict], excluded: list[Box]) -> list[Drawing]:
    """Return the flowcharts and charts drawn on this page."""
    pieces = _pieces(page, excluded)
    if len(pieces) < _MIN_DIAGRAM_SHAPES:
        return []
    found: list[Drawing] = []
    leftover: list[Box] = []
    for cluster in _clusters(pieces):
        region = _union(cluster)
        diagram = _as_diagram(cluster, region, words)
        if diagram is not None:
            found.append(diagram)
            continue
        chart = _as_chart(cluster, region, words)
        if chart is not None:
            found.append(chart)
            continue
        leftover.append(region)
    return [
        _with_neighbours(drawing, leftover, words) if drawing.kind == "diagram" else drawing
        for drawing in found
    ]


def _with_neighbours(drawing: Drawing, leftover: list[Box], words: list[dict]) -> Drawing:
    """Widen a flowchart over drawn parts set beside it, such as networks drawn side by side.

    A part joins when it sits within a short gap of the flowchart, shares
    most of its height with it, and holds words. Its words are read top to
    bottom, and the parts are read left to right.
    """
    region = drawing.box
    parts: list[tuple[float, str]] = [(region[0], drawing.text)]
    changed = True
    while changed:
        changed = False
        for part in list(leftover):
            if not _beside(part, region):
                continue
            inside = [word for word in words if _center_inside(_word_box(word), part)]
            if not inside:
                continue
            inside.sort(key=lambda word: (round(float(word["top"]) / 3), float(word["x0"])))
            parts.append((part[0], " ".join(str(word.get("text") or "") for word in inside)))
            region = _union([region, part])
            leftover.remove(part)
            changed = True
    if len(parts) == 1:
        return drawing
    parts.sort()
    return Drawing(region, drawing.kind, " | ".join(text for _left, text in parts if text))


def _beside(part: Box, region: Box) -> bool:
    gap = max(part[0] - region[2], region[0] - part[2])
    if gap > _NEIGHBOUR_GAP:
        return False
    shared = min(part[3], region[3]) - max(part[1], region[1])
    return shared >= min(part[3] - part[1], region[3] - region[1]) * 0.5


def _pieces(page, excluded: list[Box]) -> list[Box]:
    objects = list(page.rects or []) + list(page.curves or []) + list(page.lines or [])
    if len(objects) > _MAX_DRAWN_OBJECTS:
        return []
    width = float(page.width)
    height = float(page.height)
    kept: list[Box] = []
    for obj in objects:
        box = (float(obj["x0"]), float(obj["top"]), float(obj["x1"]), float(obj["bottom"]))
        if box[2] - box[0] > width * _PAGE_SPAN or box[3] - box[1] > height * _PAGE_SPAN:
            continue
        if any(_center_inside(box, region) for region in excluded):
            continue
        kept.append(box)
    return kept


def _clusters(pieces: list[Box]) -> list[list[Box]]:
    """Group pieces whose boxes touch, allowing a small slack."""
    order = sorted(range(len(pieces)), key=lambda index: pieces[index][0])
    parent = list(range(len(pieces)))

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    for position, index in enumerate(order):
        x0, top, x1, bottom = pieces[index]
        for other in order[position + 1 :]:
            ox0, otop, ox1, obottom = pieces[other]
            if ox0 > x1 + _SHAPE_SLACK:
                break
            if otop <= bottom + _SHAPE_SLACK and obottom >= top - _SHAPE_SLACK:
                parent[find(other)] = find(index)
    groups: dict[int, list[Box]] = {}
    for index, piece in enumerate(pieces):
        groups.setdefault(find(index), []).append(piece)
    return list(groups.values())


def _as_diagram(cluster: list[Box], region: Box, words: list[dict]) -> Drawing | None:
    shapes = [
        box
        for box in cluster
        if box[2] - box[0] >= _MIN_SHAPE_WIDTH
        and box[3] - box[1] >= _MIN_SHAPE_HEIGHT
        and any(_center_inside(_word_box(word), box) for word in words)
    ]
    steps = [
        shape
        for shape in shapes
        if not any(other != shape and _center_inside(other, shape) for other in shapes)
    ]
    if len(steps) < _MIN_DIAGRAM_SHAPES:
        return None
    links = sum(1 for box in cluster if _is_arrowhead(box) or _is_connector(box))
    if links < _MIN_DIAGRAM_LINKS:
        return None
    inside = [word for word in words if _center_inside(_word_box(word), region)]
    if len(inside) < _MIN_DIAGRAM_SHAPES:
        return None
    return Drawing(region, "diagram", _diagram_text(shapes, inside))


def _as_chart(cluster: list[Box], region: Box, words: list[dict]) -> Drawing | None:
    if len(cluster) < _MIN_CHART_PIECES:
        return None
    if region[2] - region[0] < _MIN_CHART_WIDTH or region[3] - region[1] < _MIN_CHART_HEIGHT:
        return None
    ticks = sum(1 for box in cluster if max(box[2] - box[0], box[3] - box[1]) <= _TICK)
    if ticks < _MIN_CHART_TICKS:
        return None
    reach = (
        region[0] - _LABEL_REACH,
        region[1] - _LABEL_REACH,
        region[2] + _LABEL_REACH,
        region[3] + _LABEL_REACH,
    )
    inside = [word for word in words if _center_inside(_word_box(word), region)]
    if inside and sum(1 for word in inside if _is_short_label(word)) < len(inside) * _SHORT_LABEL_SHARE:
        return None
    labels = [
        word
        for word in words
        if _center_inside(_word_box(word), reach) and (word in inside or _is_short_label(word))
    ]
    box = _union([region, *(_word_box(word) for word in labels)])
    return Drawing(box, "chart", "")


def _diagram_text(shapes: list[Box], words: list[dict]) -> str:
    """Read the words one shape at a time. Words outside every shape are read as their own groups."""
    by_area = sorted(shapes, key=_area)
    groups: dict[Box | None, list[dict]] = {}
    for word in words:
        home = next((shape for shape in by_area if _center_inside(_word_box(word), shape)), None)
        groups.setdefault(home, []).append(word)
    ordered: list[tuple[float, float, str]] = []
    for home, members in groups.items():
        members.sort(key=lambda word: (round(float(word["top"]) / 3), float(word["x0"])))
        text = " ".join(str(word.get("text") or "") for word in members).strip()
        if not text:
            continue
        top = home[1] if home is not None else min(float(word["top"]) for word in members)
        left = home[0] if home is not None else min(float(word["x0"]) for word in members)
        ordered.append((top, left, text))
    ordered.sort()
    return " | ".join(text for _top, _left, text in ordered)


def _is_short_label(word: dict) -> bool:
    text = str(word.get("text") or "")
    return len(text) <= _SHORT_LABEL or any(char.isdigit() for char in text)


def _is_arrowhead(box: Box) -> bool:
    width = box[2] - box[0]
    height = box[3] - box[1]
    return _ARROW_MIN <= width <= _ARROW_MAX and _ARROW_MIN <= height <= _ARROW_MAX


def _is_connector(box: Box) -> bool:
    width = box[2] - box[0]
    height = box[3] - box[1]
    return min(width, height) <= _THIN and max(width, height) >= _MIN_SHAPE_HEIGHT


def _word_box(word: dict) -> Box:
    return float(word["x0"]), float(word["top"]), float(word["x1"]), float(word["bottom"])


def _center_inside(inner: Box, outer: Box) -> bool:
    center_x = (inner[0] + inner[2]) / 2
    center_y = (inner[1] + inner[3]) / 2
    return outer[0] <= center_x <= outer[2] and outer[1] <= center_y <= outer[3]


def _union(boxes) -> Box:
    boxes = list(boxes)
    return (
        min(box[0] for box in boxes),
        min(box[1] for box in boxes),
        max(box[2] for box in boxes),
        max(box[3] for box in boxes),
    )


def _area(box: Box) -> float:
    return max(box[2] - box[0], 0.0) * max(box[3] - box[1], 0.0)
