from __future__ import annotations

import re
from typing import Optional

from app.models.domain import Citation, QueryAnswer
from parser.models import DocumentChunk, ParsedDocument


class DocumentChunker:
    """Hierarchical and semantic chunking for parsed CT-200 technical manuals."""

    def __init__(self, max_words_per_chunk: int = 150, overlap_words: int = 30):
        self.max_words_per_chunk = max_words_per_chunk
        self.overlap_words = overlap_words

    def chunk_document(self, doc: ParsedDocument) -> list[DocumentChunk]:
        chunks: list[DocumentChunk] = []
        chunk_counter = 0

        for section in doc.sections:
            if not section.content.strip():
                continue

            words = section.content.split()
            if len(words) <= self.max_words_per_chunk:
                chunk_counter += 1
                chunks.append(
                    DocumentChunk(
                        chunk_id=f"{doc.id}_sec_{section.section_number}_{chunk_counter}",
                        document_id=doc.id,
                        section_number=section.section_number,
                        section_title=section.title,
                        page_number=section.page_start,
                        text=f"Section {section.section_number} {section.title}:\n{section.content}",
                        token_count=len(words),
                    )
                )
            else:
                start = 0
                part = 1
                while start < len(words):
                    end = min(start + self.max_words_per_chunk, len(words))
                    sub_words = words[start:end]
                    chunk_text = " ".join(sub_words)
                    chunk_counter += 1

                    chunks.append(
                        DocumentChunk(
                            chunk_id=f"{doc.id}_sec_{section.section_number}_p{part}_{chunk_counter}",
                            document_id=doc.id,
                            section_number=section.section_number,
                            section_title=f"{section.title} (Part {part})",
                            page_number=section.page_start,
                            text=f"Section {section.section_number} {section.title} (Part {part}):\n{chunk_text}",
                            token_count=len(sub_words),
                        )
                    )

                    if end == len(words):
                        break
                    start += self.max_words_per_chunk - self.overlap_words
                    part += 1

        return chunks


class RAGService:
    """Retrieval-Augmented Generation service providing grounded answers with citations."""

    def __init__(self, doc_v1: Optional[ParsedDocument], doc_v2: Optional[ParsedDocument]):
        self.doc_v1 = doc_v1
        self.doc_v2 = doc_v2
        self.chunker = DocumentChunker()
        self.v1_chunks: list[DocumentChunk] = self.chunker.chunk_document(doc_v1) if doc_v1 else []
        self.v2_chunks: list[DocumentChunk] = self.chunker.chunk_document(doc_v2) if doc_v2 else []

    def answer_query(self, query: str, version: str = "v2", max_citations: int = 3) -> QueryAnswer:
        version_clean = version.lower()
        active_chunks: list[DocumentChunk] = []

        if "both" in version_clean:
            active_chunks = self.v1_chunks + self.v2_chunks
        elif "1" in version_clean:
            active_chunks = self.v1_chunks
        else:
            active_chunks = self.v2_chunks

        if not active_chunks:
            return QueryAnswer(
                query=query,
                target_version=version,
                answer="No documents are currently indexed for the requested version.",
                citations=[],
                confidence=0.0,
            )

        query_tokens = [w.lower() for w in re.findall(r"\w+", query) if len(w) > 2]
        scored_chunks: list[tuple[float, DocumentChunk]] = []

        for chunk in active_chunks:
            chunk_lower = chunk.text.lower()
            score = 0.0
            for token in query_tokens:
                if token in chunk.section_title.lower():
                    score += 3.0
                if token in chunk_lower:
                    score += 1.0

            for token in query_tokens:
                if re.match(r"^e[1-5]$", token):
                    if token.upper() in chunk.text:
                        score += 5.0

            if score > 0:
                scored_chunks.append((score, chunk))

        scored_chunks.sort(key=lambda x: x[0], reverse=True)
        top_matches = scored_chunks[:max_citations]

        if not top_matches:
            return QueryAnswer(
                query=query,
                target_version=version,
                answer=(
                    f"No direct mention found in CT-200 manual ({version}) for query: '{query}'. "
                    "Please verify your query terms against standard sections: Specifications, Operation, Alarms/Errors, or Maintenance."
                ),
                citations=[],
                confidence=0.1,
            )

        citations: list[Citation] = []
        for score, chunk in top_matches:
            snippet = chunk.text.split("\n", 1)[-1][:300].strip() + "..."
            citations.append(
                Citation(
                    document_id=chunk.document_id,
                    section_number=chunk.section_number,
                    section_title=chunk.section_title,
                    page_number=chunk.page_number,
                    snippet=snippet,
                    relevance_score=round(score, 2),
                )
            )

        best_chunk = top_matches[0][1]
        best_text = best_chunk.text

        answer = (
            f"According to Section {best_chunk.section_number} ({best_chunk.section_title}, "
            f"page {best_chunk.page_number}) of the {best_chunk.document_id.upper()} manual:\n\n"
            f"{best_text}"
        )

        return QueryAnswer(
            query=query,
            target_version=version,
            answer=answer,
            citations=citations,
            confidence=min(0.95, 0.4 + (top_matches[0][0] * 0.1)),
        )
