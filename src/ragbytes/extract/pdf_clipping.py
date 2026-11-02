"""Text a PDF paints but clips away, found with pdfium.

A text object can sit wholly outside the clipping path it is drawn under,
as when a slide is printed twice and the second copy is cut down to a small
frame. A reader never sees that text, but pdfminer reports it as if it
were on the page. pdfium knows each text object's clipping path, so each
character that falls wholly outside its object's clip region is listed
here by its text and baseline origin, to be matched against the
characters pdfminer reports.
"""

import ctypes

import pypdfium2 as pdfium
import pypdfium2.raw as pdfium_c

_ORIGIN_SLACK = 0.6
_UNCLIPPED = (float("-inf"), float("-inf"), float("inf"), float("inf"))


class Clipped:
    """The characters clipped away on one page."""

    def __init__(self, origins: dict[str, list[tuple[float, float]]]):
        self._origins = origins

    def __bool__(self) -> bool:
        return bool(self._origins)

    def hides(self, char: dict) -> bool:
        matrix = char.get("matrix")
        if not matrix:
            return False
        x, y = float(matrix[4]), float(matrix[5])
        return any(
            abs(x - hidden_x) <= _ORIGIN_SLACK and abs(y - hidden_y) <= _ORIGIN_SLACK
            for hidden_x, hidden_y in self._origins.get(char.get("text", ""), ())
        )


def open_document(data: bytes):
    """The PDF opened in pdfium, or None when pdfium cannot read it."""
    try:
        return pdfium.PdfDocument(data)
    except Exception:  # noqa: BLE001
        return None


def clipped_chars(document, index: int) -> Clipped:
    """The characters on a page that lie wholly outside their text object's clipping path.

    Only text objects set directly on the page are checked, since the
    clipping path of an object inside a form is kept in another space.
    """
    if document is None:
        return Clipped({})
    try:
        page = document[index]
    except Exception:  # noqa: BLE001
        return Clipped({})
    try:
        regions: dict[int, tuple[float, float, float, float] | None] = {}
        for item in page.get_objects(max_depth=0):
            if item.type != pdfium_c.FPDF_PAGEOBJ_TEXT:
                continue
            clip = pdfium_c.FPDFPageObj_GetClipPath(item.raw)
            region = _clip_region(clip) if clip else _UNCLIPPED
            if region != _UNCLIPPED:
                regions[_address(item.raw)] = region
        if not regions:
            return Clipped({})
        textpage = page.get_textpage()
        try:
            return Clipped(_origins(textpage, regions))
        finally:
            textpage.close()
    except Exception:  # noqa: BLE001
        return Clipped({})
    finally:
        page.close()


def _clip_region(clip) -> tuple[float, float, float, float] | None:
    """The box every path of a clipping path lets through, or None when nothing shows."""
    region = None
    for path in range(pdfium_c.FPDFClipPath_CountPaths(clip)):
        box = _path_box(clip, path)
        if box is None:
            continue
        region = box if region is None else _intersect(region, box)
        if region is None:
            return None
    return region if region is not None else _UNCLIPPED


def _path_box(clip, path: int) -> tuple[float, float, float, float] | None:
    xs: list[float] = []
    ys: list[float] = []
    for index in range(pdfium_c.FPDFClipPath_CountPathSegments(clip, path)):
        segment = pdfium_c.FPDFClipPath_GetPathSegment(clip, path, index)
        x, y = ctypes.c_float(), ctypes.c_float()
        if segment and pdfium_c.FPDFPathSegment_GetPoint(segment, x, y):
            xs.append(x.value)
            ys.append(y.value)
    if not xs:
        return None
    return min(xs), min(ys), max(xs), max(ys)


def _intersect(first, second) -> tuple[float, float, float, float] | None:
    left, bottom = max(first[0], second[0]), max(first[1], second[1])
    right, top = min(first[2], second[2]), min(first[3], second[3])
    if right <= left or top <= bottom:
        return None
    return left, bottom, right, top


def _origins(
    textpage, regions: dict[int, tuple[float, float, float, float] | None]
) -> dict[str, list[tuple[float, float]]]:
    origins: dict[str, list[tuple[float, float]]] = {}
    for index in range(pdfium_c.FPDFText_CountChars(textpage.raw)):
        owner = pdfium_c.FPDFText_GetTextObject(textpage.raw, index)
        address = _address(owner) if owner else 0
        if address not in regions:
            continue
        region = regions[address]
        if region is not None:
            left, right, bottom, top = ctypes.c_double(), ctypes.c_double(), ctypes.c_double(), ctypes.c_double()
            if not pdfium_c.FPDFText_GetCharBox(textpage.raw, index, left, right, bottom, top):
                continue
            box = (left.value, bottom.value, max(right.value, left.value + 0.01), max(top.value, bottom.value + 0.01))
            if _intersect(region, box) is not None:
                continue
        x, y = ctypes.c_double(), ctypes.c_double()
        if not pdfium_c.FPDFText_GetCharOrigin(textpage.raw, index, x, y):
            continue
        text = chr(pdfium_c.FPDFText_GetUnicode(textpage.raw, index))
        origins.setdefault(text, []).append((x.value, y.value))
    return origins


def _address(handle) -> int:
    return ctypes.cast(handle, ctypes.c_void_p).value or 0
