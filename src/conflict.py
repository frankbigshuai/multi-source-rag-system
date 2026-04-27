"""
Contradiction detection across retrieved chunks.

Strategy:
  1. Use regex patterns to extract (key, numeric_value) pairs from each chunk.
  2. When different source types report different values for the same key,
     flag a contradiction.
  3. Resolve contradictions by authority weight:
         docs (1.0) > blogs (0.6) > forums (0.3)
  4. Attach a plain-language warning to the response context.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from src.retriever import ScoredChunk
from src.utils import load_config

logger = logging.getLogger(__name__)

# Patterns: (setting_name → regex that captures one numeric value)
CONFLICT_PATTERNS: Dict[str, re.Pattern] = {
    "connection_timeout": re.compile(
        r"(?:connection[.\s_]*)?timeout[^\d]{0,20}?(\d+)\s*(?:seconds?|s\b)", re.IGNORECASE
    ),
    "max_connections": re.compile(
        r"max[_\s]*connections?[^\d]{0,10}?(\d+)", re.IGNORECASE
    ),
    "max_retries": re.compile(
        r"max[_\s]*retries?[^\d]{0,10}?(\d+)", re.IGNORECASE
    ),
    "parallelism": re.compile(
        r"parallelism[^\d]{0,10}?(\d+)", re.IGNORECASE
    ),
    "batch_size": re.compile(
        r"batch[_\s]*size[^\d]{0,10}?(\d+)", re.IGNORECASE
    ),
    "port": re.compile(
        r"\bport[^\d]{0,5}?(\d{4,5})\b", re.IGNORECASE
    ),
}


@dataclass
class ConflictReport:
    has_conflict: bool
    conflicts: List[dict] = field(default_factory=list)
    resolution_note: str = ""
    authoritative_chunks: List[ScoredChunk] = field(default_factory=list)


class ConflictDetector:
    AUTHORITY: Dict[str, float] = {"docs": 1.0, "blogs": 0.6, "forums": 0.3}

    def __init__(self, config=None):
        cfg = config or load_config()
        weights = cfg.get("conflict", {}).get("authority_weights", {})
        self.authority: Dict[str, float] = {**self.AUTHORITY, **weights}

    def detect(self, top_chunks: List[ScoredChunk]) -> ConflictReport:
        """
        Check top_chunks for contradicting values.
        Returns a ConflictReport with details and (optionally) reordered chunks
        so that higher-authority chunks come first.
        """
        # Extract (setting, value, source_type, chunk) per chunk
        findings: List[Tuple[str, str, str, ScoredChunk]] = []
        for sc in top_chunks:
            for setting, pattern in CONFLICT_PATTERNS.items():
                match = pattern.search(sc.chunk.text)
                if match:
                    findings.append((setting, match.group(1), sc.chunk.source_type, sc))

        # Group by setting, collect distinct values per source
        setting_values: Dict[str, Dict[str, List[str]]] = {}
        setting_chunks: Dict[str, Dict[str, List[ScoredChunk]]] = {}
        for setting, value, source_type, sc in findings:
            setting_values.setdefault(setting, {}).setdefault(source_type, [])
            if value not in setting_values[setting][source_type]:
                setting_values[setting][source_type].append(value)
            setting_chunks.setdefault(setting, {}).setdefault(source_type, [])
            if sc not in setting_chunks[setting][source_type]:
                setting_chunks[setting][source_type].append(sc)

        conflicts: List[dict] = []
        for setting, source_map in setting_values.items():
            all_values = {v for values in source_map.values() for v in values}
            if len(all_values) <= 1:
                continue  # no contradiction

            # Sort sources by authority (highest first)
            sources_ranked = sorted(
                source_map.keys(),
                key=lambda s: self.authority.get(s, 0.0),
                reverse=True,
            )
            authoritative_source = sources_ranked[0]
            authoritative_value = source_map[authoritative_source][0]

            conflict_detail = {
                "setting": setting,
                "values_by_source": {
                    src: vals for src, vals in source_map.items()
                },
                "authoritative_source": authoritative_source,
                "authoritative_value": authoritative_value,
                "authority_scores": {
                    src: self.authority.get(src, 0.0) for src in source_map
                },
            }
            conflicts.append(conflict_detail)
            logger.info(
                "[ConflictDetector] Conflict on '%s': %s. Trusting '%s'=%s (authority=%.1f)",
                setting,
                {s: v for s, v in source_map.items()},
                authoritative_source,
                authoritative_value,
                self.authority.get(authoritative_source, 0),
            )

        resolution_note = self._build_resolution_note(conflicts)

        # Re-order top_chunks: higher-authority first (for prompt context)
        sorted_chunks = sorted(
            top_chunks,
            key=lambda sc: self.authority.get(sc.chunk.source_type, 0.0),
            reverse=True,
        )

        return ConflictReport(
            has_conflict=bool(conflicts),
            conflicts=conflicts,
            resolution_note=resolution_note,
            authoritative_chunks=sorted_chunks,
        )

    @staticmethod
    def _build_resolution_note(conflicts: List[dict]) -> str:
        if not conflicts:
            return ""
        notes: List[str] = []
        for c in conflicts:
            source_details = ", ".join(
                f"{src}: {'/'.join(vals)}"
                for src, vals in c["values_by_source"].items()
            )
            notes.append(
                f"Conflicting '{c['setting']}' values ({source_details}). "
                f"Trusting {c['authoritative_source']} value: {c['authoritative_value']}."
            )
        return " | ".join(notes)


def format_conflicts_for_user(report: ConflictReport) -> Optional[str]:
    """Returns a human-readable conflict warning, or None if no conflicts."""
    if not report.has_conflict:
        return None
    lines = ["⚠ Source Conflict Detected:"]
    for c in report.conflicts:
        for src, vals in c["values_by_source"].items():
            lines.append(f"  • {src} says {c['setting']} = {', '.join(vals)}")
        lines.append(
            f"  → Trusting {c['authoritative_source']} "
            f"(authority {c['authority_scores'][c['authoritative_source']]:.1f}): "
            f"{c['authoritative_value']}"
        )
    return "\n".join(lines)
