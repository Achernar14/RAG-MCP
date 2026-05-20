"""Whitespace-aware chunk splitter with lightweight refinement."""

from __future__ import annotations

import re

from rag_mcp.domain.entities.models import Chunk, Document


class SimpleTextSplitter:
    """Split text into refined overlapping chunks with natural boundaries."""

    def __init__(
        self,
        chunk_size: int,
        chunk_overlap: int,
        *,
        normalize_whitespace: bool = True,
        preserve_paragraph_breaks: bool = True,
        boundary_scan_chars: int = 80,
        min_chunk_length: int = 40,
    ) -> None:
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.normalize_whitespace = normalize_whitespace
        self.preserve_paragraph_breaks = preserve_paragraph_breaks
        self.boundary_scan_chars = boundary_scan_chars
        self.min_chunk_length = min_chunk_length

    def split(self, document: Document) -> list[Chunk]:
        """Split a document into refined chunks."""
        content = self._normalize_content(document.content)
        if not content:
            return []

        document.content = content
        chunks: list[Chunk] = []
        start = 0
        index = 0
        while start < len(content):
            nominal_end = min(start + self.chunk_size, len(content))
            end = self._refine_end_boundary(content, start, nominal_end)
            raw_text = content[start:end]
            stripped_text = raw_text.strip()
            is_last_segment = end >= len(content)
            if stripped_text and (len(stripped_text) >= self.min_chunk_length or (is_last_segment and not chunks)):
                text_start = start + raw_text.index(stripped_text)
                text_end = text_start + len(stripped_text)
                chunks.append(
                    Chunk(
                        id=f"{document.id}:{index}",
                        document_id=document.id,
                        text=stripped_text,
                        chunk_index=index,
                        start_offset=text_start,
                        end_offset=text_end,
                        metadata={
                            "document_id": document.id,
                            "source_path": document.source_path,
                            "chunk_index": index,
                        },
                    )
                )
                index += 1

            if end >= len(content):
                break

            next_start = self._refine_next_start(content, end)
            overlap_start = max(next_start - self.chunk_overlap, start + 1)
            start = self._refine_next_start(content, overlap_start)
            if start >= end:
                start = min(end, len(content))
        return chunks

    def _normalize_content(self, content: str) -> str:
        """Normalize raw content while keeping enough structure for retrieval."""
        normalized = content.replace("\r\n", "\n").replace("\r", "\n")
        normalized = normalized.replace("\t", " ")
        if self.normalize_whitespace:
            normalized = self._collapse_spaces(normalized)
        if self.preserve_paragraph_breaks:
            normalized = re.sub(r"\n{3,}", "\n\n", normalized)
        else:
            normalized = normalized.replace("\n", " ")
            normalized = re.sub(r" {2,}", " ", normalized)
        return normalized.strip()

    def _collapse_spaces(self, content: str) -> str:
        """Collapse repeated spaces but preserve line breaks."""
        lines = [re.sub(r"[ \u00A0]+", " ", line).strip() for line in content.split("\n")]
        return "\n".join(lines)

    def _refine_end_boundary(self, content: str, start: int, nominal_end: int) -> int:
        """Prefer paragraph, sentence, or whitespace boundaries near the nominal end."""
        if nominal_end >= len(content):
            return len(content)

        window_end = min(len(content), nominal_end + self.boundary_scan_chars)
        paragraph_break = content.find("\n\n", nominal_end, window_end)
        if paragraph_break != -1 and paragraph_break > start:
            return paragraph_break

        boundary_chars = {".", "!", "?", "。", "！", "？", "\n", " "}
        preferred_sentence_end = -1
        for index in range(window_end - 1, nominal_end - 1, -1):
            if content[index] in {".", "!", "?", "。", "！", "？"} and index > start:
                preferred_sentence_end = index + 1
                break
        if preferred_sentence_end != -1:
            return preferred_sentence_end
        for index in range(nominal_end, window_end):
            if content[index] in boundary_chars and index > start:
                return index + 1
        return nominal_end

    def _refine_next_start(self, content: str, candidate_start: int) -> int:
        """Advance the next chunk start to a readable boundary."""
        if candidate_start >= len(content):
            return len(content)
        while candidate_start < len(content) and content[candidate_start].isspace():
            candidate_start += 1
        return candidate_start
