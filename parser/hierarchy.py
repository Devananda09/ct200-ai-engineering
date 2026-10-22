from __future__ import annotations

from parser.models import DocumentNode, DocumentSection


def build_hierarchy(sections: list[DocumentSection]) -> list[DocumentNode]:
    """
    Convert flat document sections into a hierarchical tree.

    The original section order is preserved.

    Example:

        1
        ├── 1.1
        └── 1.2

        2
        ├── 2.1
        │   └── 2.1.1.1
        └── 2.2

    Missing intermediate parents are allowed. For example,
    2.1.1.1 can exist even when 2.1.1 is not present.
    """

    nodes: dict[str, DocumentNode] = {}
    roots: list[DocumentNode] = []

    for section in sections:
        node = DocumentNode(
            node_id=section.section_number,
            heading=section.title,
            level=section.level,
            body_text=section.content,
            page_number=section.page_start,
        )

        nodes[section.section_number] = node

        parent_number = _find_existing_parent(
            section.section_number,
            nodes,
        )

        if parent_number is None:
            roots.append(node)
        else:
            parent = nodes[parent_number]
            node.parent_id = parent.node_id
            parent.children.append(node)

    return roots


def _find_existing_parent(
    section_number: str,
    nodes: dict[str, DocumentNode],
) -> str | None:
    """
    Find the nearest existing parent section.

    For example:

        section = 2.1.1.1
        existing sections = 2, 2.1

    Result:

        2.1

    This allows missing intermediate sections such as 2.1.1.
    """

    parts = section_number.split(".")

    if len(parts) <= 1:
        return None

    for i in range(len(parts) - 1, 0, -1):
        candidate = ".".join(parts[:i])

        if candidate in nodes:
            return candidate

    return None