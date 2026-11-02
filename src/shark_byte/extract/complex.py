"""The pass that receives regions the structural walk could not read.

The walk has already taken the readable rows, pictures, and charts out of a
table or figure. What remains is one complex section per unread cell or
layout. This pass is where a later reader can turn that leftover into text.
Until then the region stays whole, with its original markup beside the marker.
"""

from shark_byte.extract.sections import assign_indexes
from shark_byte.schemas import Section


def prepare_for_chunking(sections: list[Section]) -> list[Section]:
    """Run the complex pass, leaving every readable section where it is."""
    prepared: list[Section] = []
    changed = False
    for section in sections:
        if section.kind != "complex":
            prepared.append(section)
            continue
        pieces = read_complex(section)
        if pieces != [section]:
            changed = True
        prepared.extend(pieces)
    if changed:
        return assign_indexes(prepared)
    return prepared


def read_complex(section: Section) -> list[Section]:
    """Return the unread region.

    A later reader can split this section. The markup stays on ``media``.
    """
    return [section]
