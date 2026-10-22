from __future__ import annotations

import difflib
from typing import Optional

from parser.models import (
    DocumentComparisonResult,
    ParameterDiff,
    ParsedDocument,
    SectionDiff,
)


class DocumentComparator:
    """Compares two parsed versions of the CT-200 technical manual."""

    @classmethod
    def compare(
        cls,
        doc_v1: ParsedDocument,
        doc_v2: ParsedDocument,
    ) -> DocumentComparisonResult:

        v1_sections = {
            section.section_number: section
            for section in doc_v1.sections
        }

        v2_sections = {
            section.section_number: section
            for section in doc_v2.sections
        }

        def sort_key(section_number: str) -> list[int]:
            parts = []

            for part in section_number.split("."):
                parts.append(int(part) if part.isdigit() else 0)

            return parts

        all_section_numbers = sorted(
            set(v1_sections.keys()).union(v2_sections.keys()),
            key=sort_key,
        )

        section_diffs: list[SectionDiff] = []

        sections_added: list[str] = []
        sections_removed: list[str] = []
        sections_modified: list[str] = []

        summary_points: list[str] = []

        for section_number in all_section_numbers:

            section_v1 = v1_sections.get(section_number)
            section_v2 = v2_sections.get(section_number)

            # Section added
            if section_v1 is None and section_v2 is not None:

                sections_added.append(section_number)

                section_diffs.append(
                    SectionDiff(
                        section_number=section_number,
                        title=section_v2.title,
                        status="added",
                        v1_content=None,
                        v2_content=section_v2.content,
                        changes_summary=[
                            f"New section '{section_v2.title}' added in {doc_v2.version}"
                        ],
                    )
                )

                summary_points.append(
                    f"Added section {section_number}: '{section_v2.title}'"
                )

            # Section removed
            elif section_v1 is not None and section_v2 is None:

                sections_removed.append(section_number)

                section_diffs.append(
                    SectionDiff(
                        section_number=section_number,
                        title=section_v1.title,
                        status="removed",
                        v1_content=section_v1.content,
                        v2_content=None,
                        changes_summary=[
                            f"Section '{section_v1.title}' removed in {doc_v2.version}"
                        ],
                    )
                )

                summary_points.append(
                    f"Removed section {section_number}: '{section_v1.title}'"
                )

            # Section exists in both versions
            elif section_v1 is not None and section_v2 is not None:

                content_v1 = " ".join(section_v1.content.split())
                content_v2 = " ".join(section_v2.content.split())

                if content_v1 != content_v2:

                    sections_modified.append(section_number)

                    changes: list[str] = []

                    if section_v1.title != section_v2.title:
                        changes.append(
                            f"Title changed from '{section_v1.title}' "
                            f"to '{section_v2.title}'"
                        )

                    matcher = difflib.SequenceMatcher(
                        None,
                        section_v1.content.split(),
                        section_v2.content.split(),
                    )

                    diff_blocks: list[str] = []

                    for tag, i1, i2, j1, j2 in matcher.get_opcodes():

                        if tag == "replace":

                            diff_blocks.append(
                                f"Changed "
                                f"'{ ' '.join(section_v1.content.split()[i1:i2]) }' "
                                f"-> "
                                f"'{ ' '.join(section_v2.content.split()[j1:j2]) }'"
                            )

                        elif tag == "insert":

                            diff_blocks.append(
                                f"Inserted "
                                f"'{ ' '.join(section_v2.content.split()[j1:j2]) }'"
                            )

                        elif tag == "delete":

                            diff_blocks.append(
                                f"Deleted "
                                f"'{ ' '.join(section_v1.content.split()[i1:i2]) }'"
                            )

                    changes.extend(diff_blocks[:5])

                    section_diffs.append(
                        SectionDiff(
                            section_number=section_number,
                            title=section_v2.title,
                            status="modified",
                            v1_content=section_v1.content,
                            v2_content=section_v2.content,
                            changes_summary=changes,
                        )
                    )

                    summary_points.append(
                        f"Modified section {section_number} "
                        f"({section_v2.title})"
                    )

                else:

                    section_diffs.append(
                        SectionDiff(
                            section_number=section_number,
                            title=section_v1.title,
                            status="unchanged",
                            v1_content=section_v1.content,
                            v2_content=section_v2.content,
                            changes_summary=[],
                        )
                    )

        # Compare parameters
        v1_parameters = {
            parameter.parameter: parameter.value
            for parameter in doc_v1.parameters
        }

        v2_parameters = {
            parameter.parameter: parameter.value
            for parameter in doc_v2.parameters
        }

        all_parameter_names = sorted(
            set(v1_parameters.keys()).union(v2_parameters.keys())
        )

        parameter_diffs: list[ParameterDiff] = []

        for parameter_name in all_parameter_names:

            v1_value = v1_parameters.get(parameter_name)
            v2_value = v2_parameters.get(parameter_name)

            if v1_value is None and v2_value is not None:

                parameter_diffs.append(
                    ParameterDiff(
                        parameter=parameter_name,
                        status="added",
                        v1_value=None,
                        v2_value=v2_value,
                        details="Newly introduced parameter",
                    )
                )

                summary_points.append(
                    f"New parameter added: "
                    f"{parameter_name} = {v2_value}"
                )

            elif v1_value is not None and v2_value is None:

                parameter_diffs.append(
                    ParameterDiff(
                        parameter=parameter_name,
                        status="removed",
                        v1_value=v1_value,
                        v2_value=None,
                        details="Parameter removed",
                    )
                )

                summary_points.append(
                    f"Parameter removed: {parameter_name}"
                )

            elif v1_value != v2_value:

                parameter_diffs.append(
                    ParameterDiff(
                        parameter=parameter_name,
                        status="modified",
                        v1_value=v1_value,
                        v2_value=v2_value,
                        details=(
                            f"Changed from '{v1_value}' "
                            f"to '{v2_value}'"
                        ),
                    )
                )

                summary_points.append(
                    f"Parameter changed: {parameter_name}: "
                    f"'{v1_value}' -> '{v2_value}'"
                )

            else:

                parameter_diffs.append(
                    ParameterDiff(
                        parameter=parameter_name,
                        status="unchanged",
                        v1_value=v1_value,
                        v2_value=v2_value,
                        details="No change",
                    )
                )

        return DocumentComparisonResult(
            doc_v1_id=doc_v1.id,
            doc_v2_id=doc_v2.id,
            sections_added=sections_added,
            sections_removed=sections_removed,
            sections_modified=sections_modified,
            section_diffs=section_diffs,
            parameter_diffs=parameter_diffs,
            summary_points=summary_points,
        )


class DiffService:
    """Service to calculate and cache differences between two manuals."""

    def __init__(
        self,
        doc_v1: Optional[ParsedDocument],
        doc_v2: Optional[ParsedDocument],
    ):
        self.doc_v1 = doc_v1
        self.doc_v2 = doc_v2
        self._cached_diff: Optional[DocumentComparisonResult] = None

    def get_diff(self) -> DocumentComparisonResult:

        if self._cached_diff is not None:
            return self._cached_diff

        if self.doc_v1 is None or self.doc_v2 is None:
            raise ValueError(
                "Both v1 and v2 manuals must be loaded "
                "to calculate differences."
            )

        self._cached_diff = DocumentComparator.compare(
            self.doc_v1,
            self.doc_v2,
        )

        return self._cached_diff