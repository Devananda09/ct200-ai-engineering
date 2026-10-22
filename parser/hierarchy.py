from __future__ import annotations

from parser.models import DocumentNode, DocumentSection


import hashlib

def build_hierarchy(
    sections: list[DocumentSection],
    tables: list[dict] | None = None,
) -> list[DocumentNode]:
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

    tables_by_page: dict[int, list[dict]] = {}
    if tables:
        for tab in tables:
            pg = tab.get("page_number", 1)
            tables_by_page.setdefault(pg, []).append(tab)

    for section in sections:
        # Compute deterministic SHA-256 content hash
        hash_digest = hashlib.sha256(section.content.encode("utf-8")).hexdigest()

        # Check for matching tables on the section's pages
        section_tables: list[dict] = []
        for p in range(section.page_start, section.page_end + 1):
            if p in tables_by_page:
                section_tables.extend(tables_by_page[p])

        node = DocumentNode(
            node_id=section.section_number,
            heading=section.title,
            level=section.level,
            body_text=section.content,
            content_hash=hash_digest,
            page_number=section.page_start,
            tables=section_tables,
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


def find_node(nodes: list[DocumentNode], node_id: str) -> DocumentNode | None:
    """Recursively search for a node by node_id in the hierarchy tree."""
    for node in nodes:
        if node.node_id == node_id:
            return node
        found = find_node(node.children, node_id)
        if found:
            return found
    return None