"""
Three chunking strategies tailored to each data source type.

- DocChunker:   splits Markdown by headers (##, ###)
- ForumChunker: each Q&A post becomes one chunk
- BlogChunker:  sliding window — 200 words, 50-word overlap
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List


@dataclass
class Chunk:
    chunk_id: str
    text: str
    source_type: str        # "docs" | "forums" | "blogs"
    source_file: str
    metadata: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Markdown / documentation chunker
# ---------------------------------------------------------------------------

class DocChunker:
    """Split a Markdown file on heading boundaries (## or ###)."""

    MIN_CHARS = 80          # skip chunks that are essentially empty headings

    def chunk_file(self, filepath: Path) -> List[Chunk]:
        text = filepath.read_text(encoding="utf-8")
        return self._split_by_headers(text, str(filepath))

    def _split_by_headers(self, text: str, source_file: str) -> List[Chunk]:
        # Match any heading level (# through ####)
        header_pattern = re.compile(r"^(#{1,4}\s+.+)$", re.MULTILINE)
        positions = [m.start() for m in header_pattern.finditer(text)]
        positions.append(len(text))  # sentinel

        chunks: List[Chunk] = []
        for i, start in enumerate(positions[:-1]):
            end = positions[i + 1]
            section_text = text[start:end].strip()
            if len(section_text) < self.MIN_CHARS:
                continue

            heading_match = header_pattern.match(section_text)
            heading = heading_match.group(1).strip() if heading_match else "section"
            chunk_id = f"docs_{Path(source_file).stem}_{i:03d}"

            chunks.append(Chunk(
                chunk_id=chunk_id,
                text=section_text,
                source_type="docs",
                source_file=source_file,
                metadata={"heading": heading, "section_index": i},
            ))
        return chunks


# ---------------------------------------------------------------------------
# Forum / Q&A chunker
# ---------------------------------------------------------------------------

class ForumChunker:
    """Each forum post (question + answer) becomes one chunk."""

    def chunk_file(self, filepath: Path) -> List[Chunk]:
        posts = json.loads(filepath.read_text(encoding="utf-8"))
        chunks: List[Chunk] = []
        for post in posts:
            text = self._format_post(post)
            chunks.append(Chunk(
                chunk_id=post["post_id"],
                text=text,
                source_type="forums",
                source_file=str(filepath),
                metadata={
                    "title": post["title"],
                    "votes": post["votes"],
                    "accepted": post["accepted"],
                    "tags": post.get("tags", []),
                    "date": post.get("date", ""),
                },
            ))
        return chunks

    @staticmethod
    def _format_post(post: dict) -> str:
        lines = [
            f"Title: {post['title']}",
            f"Question: {post['question']}",
            f"Answer: {post['answer']}",
        ]
        if post.get("tags"):
            lines.append(f"Tags: {', '.join(post['tags'])}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Blog / long-form text chunker
# ---------------------------------------------------------------------------

class BlogChunker:
    """
    Sliding-window word chunker.
    window_size=200 words, overlap=50 words.
    """

    def __init__(self, window_size: int = 200, overlap: int = 50):
        self.window_size = window_size
        self.overlap = overlap

    def chunk_file(self, filepath: Path) -> List[Chunk]:
        text = filepath.read_text(encoding="utf-8")
        words = text.split()
        stem = filepath.stem
        chunks: List[Chunk] = []

        step = self.window_size - self.overlap
        start = 0
        idx = 0
        while start < len(words):
            end = min(start + self.window_size, len(words))
            chunk_text = " ".join(words[start:end])
            chunks.append(Chunk(
                chunk_id=f"blogs_{stem}_{idx:03d}",
                text=chunk_text,
                source_type="blogs",
                source_file=str(filepath),
                metadata={
                    "word_start": start,
                    "word_end": end,
                    "chunk_index": idx,
                },
            ))
            if end == len(words):
                break
            start += step
            idx += 1

        return chunks


# ---------------------------------------------------------------------------
# Unified entry point
# ---------------------------------------------------------------------------

def load_all_chunks(data_dir: str = "data") -> List[Chunk]:
    """Load and chunk all files from data/docs, data/forums, data/blogs."""
    base = Path(data_dir)
    all_chunks: List[Chunk] = []

    doc_chunker = DocChunker()
    for md_file in sorted((base / "docs").glob("*.md")):
        all_chunks.extend(doc_chunker.chunk_file(md_file))

    forum_chunker = ForumChunker()
    for json_file in sorted((base / "forums").glob("*.json")):
        all_chunks.extend(forum_chunker.chunk_file(json_file))

    blog_chunker = BlogChunker()
    for txt_file in sorted((base / "blogs").glob("*.txt")):
        all_chunks.extend(blog_chunker.chunk_file(txt_file))

    return all_chunks
