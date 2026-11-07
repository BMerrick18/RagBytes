"""Vector drawings on a PDF page: flowcharts and plotted charts.

A drawing is found by joining the page's drawn shapes, lines, and curves
that touch one another into clusters. A cluster is a flowchart when three
or more of its shapes hold text without enclosing another such shape, and
three or more of its pieces are connectors or arrowheads. A frame drawn
around a slide encloses the shapes on it, so it is not a step. When the
same frame size appears more than once on the page, as on a slide handout,
the flowchart reaches only as far as its steps and links, so the slide's
other text stays text. A lone figure's outline keeps the words around its
steps. Drawn parts set close beside a flowchart and holding words join it.
A cluster with no steps is still a flow when several arrowheads lead
between short labels, as in a network drawn as a column of labelled arrows;
its words are read in page order. A cluster is a chart when it has many
pieces, several of them axis ticks, and the words on it are mostly short
labels such as numbers and units. A chart is preferred over a flow, so a
histogram's bars are not read as arrowheads. A chart keeps no text of its
own; its caption is attached by the page walk. Shapes inside a table or an
embedded picture, and rules that span most of the page, are not part of
any drawing.
"""

from typing import NamedTuple

_MIN_SHAPE_WIDTH = 20.0
_MIN_SHAPE_HEIGHT = 10.0
_MIN_DIAGRAM_SHAPES = 3
_MIN_DIAGRAM_LINKS = 3
# A cluster with this many arrowheads between short labels is a flow even without boxes.
_MIN_FLOW_ARROWS = 5
_FLOW_WORDS_PER_ARROW = 4
_FLOW_LABEL_SHARE = 0.9
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
# A path whose last point lands this close to its first is closed.
_CLOSE_TOLERANCE = 0.5
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
    pieces, strokes = _pieces(page, excluded)
    if len(pieces) < _MIN_DIAGRAM_SHAPES:
        return []
    found: list[Drawing] = []
    leftover: list[Box] = []
    clusters = _clusters(pieces)
    shapes_by_cluster = [_cluster_shapes(cluster, words, strokes) for cluster in clusters]
    slide_sizes = _slide_sizes(shapes_by_cluster)
    for cluster, shapes in zip(clusters, shapes_by_cluster, strict=True):
        region = _union(cluster)
        diagram = _as_diagram(cluster, region, words, strokes, shapes, slide_sizes)
        if diagram is not None:
            found.append(diagram)
            continue
        chart = _as_chart(cluster, region, words)
        if chart is not None:
            found.append(chart)
            continue
        flow = _as_flow(cluster, region, words)
        if flow is not None:
            found.append(flow)
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


def _pieces(page, excluded: list[Box]) -> tuple[list[Box], set[Box]]:
    """The drawn pieces on the page, and which of them are open strokes.

    An open stroke is a line or an unfilled curve that does not close on
    itself: a connector between the steps of a flowchart, however it bends.
    A filled or closed path is a step, or decoration.
    """
    objects = (
        [(obj, False) for obj in page.rects or []]
        + [(obj, not obj.get("fill") and not _is_closed(obj)) for obj in page.curves or []]
        + [(obj, True) for obj in page.lines or []]
    )
    if len(objects) > _MAX_DRAWN_OBJECTS:
        return [], set()
    width = float(page.width)
    height = float(page.height)
    kept: list[Box] = []
    strokes: set[Box] = set()
    for obj, open_stroke in objects:
        box = (float(obj["x0"]), float(obj["top"]), float(obj["x1"]), float(obj["bottom"]))
        if box[2] - box[0] > width * _PAGE_SPAN or box[3] - box[1] > height * _PAGE_SPAN:
            continue
        if any(_center_inside(box, region) for region in excluded):
            continue
        kept.append(box)
        if open_stroke:
            strokes.add(box)
    return kept, strokes


def _is_closed(curve: dict) -> bool:
    """The path closes with ``h`` or ends where it began."""
    path = curve.get("path") or []
    if path and path[-1][0] == "h":
        return True
    pts = curve.get("pts") or []
    if len(pts) < 3:
        return False
    (x0, y0), (x1, y1) = pts[0], pts[-1]
    return abs(x0 - x1) <= _CLOSE_TOLERANCE and abs(y0 - y1) <= _CLOSE_TOLERANCE


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


def _cluster_shapes(cluster: list[Box], words: list[dict], strokes: set[Box]) -> list[Box]:
    """Shapes that hold a word and are not open strokes, so a connector is not a step."""
    return [
        box
        for box in cluster
        if box[2] - box[0] >= _MIN_SHAPE_WIDTH
        and box[3] - box[1] >= _MIN_SHAPE_HEIGHT
        and box not in strokes
        and any(_center_inside(_word_box(word), box) for word in words)
    ]


def _frames(shapes: list[Box]) -> list[Box]:
    """Shapes that enclose the centres of two or more other shapes, such as a slide border."""
    return [
        shape
        for shape in shapes
        if sum(1 for other in shapes if other != shape and _center_inside(other, shape)) >= 2
    ]


def _frame_size(box: Box) -> tuple[int, int]:
    """A frame's size in tens of points, so copies of a slide still match."""
    return round((box[2] - box[0]) / 10), round((box[3] - box[1]) / 10)


def _slide_sizes(shapes_by_cluster: list[list[Box]]) -> set[tuple[int, int]]:
    """Frame sizes that appear on more than one cluster, as on a slide handout.

    A lecture slide printed several times on one page has the same border
    around each copy. A lone figure's outline is not a slide, even when it
    holds several labelled boxes, so that figure keeps the words around its
    steps.
    """
    sizes = [_frame_size(frame) for shapes in shapes_by_cluster for frame in _frames(shapes)]
    return {size for size in set(sizes) if sizes.count(size) >= 2}


def _as_diagram(
    cluster: list[Box],
    region: Box,
    words: list[dict],
    strokes: set[Box] = frozenset(),
    shapes: list[Box] | None = None,
    slide_sizes: set[tuple[int, int]] | None = None,
) -> Drawing | None:
    if shapes is None:
        shapes = _cluster_shapes(cluster, words, strokes)
    frames = _frames(shapes)
    boxes = [shape for shape in shapes if shape not in frames]
    steps = [shape for shape in boxes if not any(other != shape and _center_inside(other, shape) for other in boxes)]
    if len(steps) < _MIN_DIAGRAM_SHAPES:
        return None
    links = [
        box
        for box in cluster
        if (_is_arrowhead(box) or _is_connector(box) or _is_open_link(box, strokes))
        and any(_touches(box, step) for step in steps)
    ]
    if len(links) < _MIN_DIAGRAM_LINKS:
        return None
    if frames and slide_sizes and any(_frame_size(frame) in slide_sizes for frame in frames):
        region = _framed_region(region, steps, links)
    inside = [word for word in words if _center_inside(_word_box(word), region)]
    if len(inside) < _MIN_DIAGRAM_SHAPES:
        return None
    return Drawing(region, "diagram", _diagram_text(shapes, inside))


def _as_flow(cluster: list[Box], region: Box, words: list[dict]) -> Drawing | None:
    """A column or row of short labels joined by arrowheads, with no boxes drawn around them.

    Nearly every word is a label, and there is an arrowhead for every few
    words. A passage with drawn bullets has arrowhead-sized marks too, but
    far more words than marks, and most of them are prose.
    """
    arrows = sum(1 for box in cluster if _is_arrowhead(box))
    if arrows < _MIN_FLOW_ARROWS:
        return None
    inside = [word for word in words if _center_inside(_word_box(word), region)]
    if len(inside) < _MIN_DIAGRAM_SHAPES or arrows * _FLOW_WORDS_PER_ARROW < len(inside):
        return None
    if sum(1 for word in inside if _is_short_label(word)) < len(inside) * _FLOW_LABEL_SHARE:
        return None
    if sum(1 for word in inside if _mostly_numeric(word)) >= len(inside) * 0.5:
        return None
    return Drawing(region, "diagram", _diagram_text([], inside))


def _framed_region(region: Box, steps: list[Box], links: list[Box]) -> Box:
    """The diagram's own extent inside a frame, such as a slide's border.

    A frame is a shape holding the centers of two or more other shapes.
    Inside one, the diagram reaches only as far as its steps and links, so
    the frame's other text stays text.
    """
    tight = _union(steps + links)
    return (
        max(region[0], tight[0] - _SHAPE_SLACK),
        max(region[1], tight[1] - _SHAPE_SLACK),
        min(region[2], tight[2] + _SHAPE_SLACK),
        min(region[3], tight[3] + _SHAPE_SLACK),
    )


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


def _mostly_numeric(word: dict) -> bool:
    """A tick, a count, or an axis label: digits, with no more letters than digits."""
    text = str(word.get("text") or "")
    digits = sum(char.isdigit() for char in text)
    letters = sum(char.isalpha() for char in text)
    return digits > 0 and digits >= letters


def _is_arrowhead(box: Box) -> bool:
    width = box[2] - box[0]
    height = box[3] - box[1]
    return _ARROW_MIN <= width <= _ARROW_MAX and _ARROW_MIN <= height <= _ARROW_MAX


def _is_connector(box: Box) -> bool:
    width = box[2] - box[0]
    height = box[3] - box[1]
    return min(width, height) <= _THIN and max(width, height) >= _MIN_SHAPE_HEIGHT


def _is_open_link(box: Box, strokes: set[Box]) -> bool:
    """An open stroke that bends between steps, such as an elbow connector, is a link.

    Its box is neither thin nor an arrowhead, but it is not a step either.
    """
    if box not in strokes or _is_connector(box) or _is_arrowhead(box):
        return False
    return max(box[2] - box[0], box[3] - box[1]) >= _MIN_SHAPE_HEIGHT


def _touches(box: Box, shape: Box) -> bool:
    return (
        box[0] <= shape[2] + _SHAPE_SLACK
        and box[2] >= shape[0] - _SHAPE_SLACK
        and box[1] <= shape[3] + _SHAPE_SLACK
        and box[3] >= shape[1] - _SHAPE_SLACK
    )


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
