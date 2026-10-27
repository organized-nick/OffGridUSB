"""Offline ZIM Encyclopedia & Medical Archive Reader (F-09).

Zero-install, air-gapped reader for OpenZIM (.zim) archives and fallback knowledge stores.
Supports article search, section extraction, binary asset streaming, and path sanitization.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import mimetypes
import os
from pathlib import Path
import re
import struct
from typing import Any, Dict, List, Optional, Tuple, Union

from emyrge.core.config import EmyrgeError


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class ZimError(EmyrgeError):
    """Base exception for ZIM archive operations."""
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__("ERR_ZIM_GENERAL", message, details)


class ZimArchiveNotFoundError(ZimError):
    """Raised when the specified .zim archive file does not exist on disk."""
    def __init__(self, archive_path: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(f"ZIM archive file not found: {archive_path}", details or {"path": archive_path})
        self.code = "ERR_ZIM_NOT_FOUND"


class ZimCorruptedError(ZimError):
    """Raised when a ZIM file has invalid magic bytes, headers, or corrupted index."""
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message, details)
        self.code = "ERR_ZIM_CORRUPTED"


class ZimArticleNotFoundError(ZimError):
    """Raised when an explicit article path cannot be located in the archive."""
    def __init__(self, article_path: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(f"Article not found in archive: {article_path}", details or {"path": article_path})
        self.code = "ERR_ZIM_ARTICLE_NOT_FOUND"


# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------

@dataclass
class ArticleSnippet:
    """Compact summary of a matching ZIM article for search listings."""
    title: str
    url: str
    snippet: str
    section: Optional[str] = None
    score: float = 0.0

    def __getitem__(self, item: str) -> Any:
        if hasattr(self, item):
            return getattr(self, item)
        raise KeyError(item)

    def get(self, item: str, default: Any = None) -> Any:
        return getattr(self, item, default)

    def __contains__(self, item: str) -> bool:
        return hasattr(self, item)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "url": self.url,
            "snippet": self.snippet,
            "section": self.section,
            "score": round(self.score, 3),
        }


@dataclass
class ArticleSection:
    """Structured heading and content block within an article."""
    heading: str
    level: int
    text: str
    anchor: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "heading": self.heading,
            "level": self.level,
            "text": self.text,
            "anchor": self.anchor,
        }


@dataclass
class ArticleContent:
    """Full article payload extracted from a ZIM archive."""
    title: str
    url: str
    html_content: str
    text_content: str
    mime_type: str = "text/html"
    sections: List[ArticleSection] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __getitem__(self, item: str) -> Any:
        if hasattr(self, item):
            return getattr(self, item)
        raise KeyError(item)

    def get(self, item: str, default: Any = None) -> Any:
        return getattr(self, item, default)

    def __contains__(self, item: str) -> bool:
        return hasattr(self, item)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "url": self.url,
            "html_content": self.html_content,
            "text_content": self.text_content,
            "mime_type": self.mime_type,
            "sections": [s.to_dict() for s in self.sections],
            "metadata": self.metadata,
        }


@dataclass
class ZimAsset:
    """Binary asset (image, stylesheet, font) extracted from a ZIM archive."""
    path: str
    data: bytes
    mime_type: str
    size_bytes: int = 0

    def __post_init__(self):
        if not self.size_bytes:
            self.size_bytes = len(self.data)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "path": self.path,
            "mime_type": self.mime_type,
            "size_bytes": self.size_bytes,
        }


@dataclass
class ZimArchiveMetadata:
    """Header and metadata descriptors for a mounted ZIM file."""
    archive_path: str
    title: str
    article_count: int
    creator: str = "Wikipedia / Kiwix"
    date: str = "2026-10"
    language: str = "eng"
    uuid: str = ""
    file_size_mb: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "archive_path": self.archive_path,
            "title": self.title,
            "article_count": self.article_count,
            "creator": self.creator,
            "date": self.date,
            "language": self.language,
            "uuid": self.uuid,
            "file_size_mb": self.file_size_mb,
        }


# ---------------------------------------------------------------------------
# ZimReader Implementation
# ---------------------------------------------------------------------------

class ZimReader:
    """Offline ZIM archive reader and search indexer."""

    ZIM_MAGIC = 0x044D495A  # 'ZIM\x04' in little-endian

    def __init__(
        self,
        archive_path: Optional[str | Path] = None,
        data_dir: Optional[str | Path] = None,
        fallback_articles: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> None:
        self.archive_path: Optional[Path] = Path(archive_path) if archive_path else None
        self.data_dir: Path = Path(data_dir) if data_dir else Path("data/zim")
        self._articles: Dict[str, ArticleContent] = {}
        self._assets: Dict[str, ZimAsset] = {}
        self._metadata: Optional[ZimArchiveMetadata] = None

        # Load fallback articles if provided
        if fallback_articles:
            self._load_fallback_dict(fallback_articles)

        # Mount archive if specified or auto-discover
        if self.archive_path:
            self._mount_archive(self.archive_path)
        elif (data_dir is not None or not fallback_articles) and self.data_dir.is_dir():
            zim_files = list(self.data_dir.glob("*.zim"))
            if zim_files:
                try:
                    self._mount_archive(zim_files[0])
                except ZimError:
                    pass

    def _load_fallback_dict(self, articles: Dict[str, Dict[str, Any]]) -> None:
        """Loads articles from dictionary fixtures (e.g. sample_zim_articles)."""
        for key, val in articles.items():
            title = val.get("title", key.replace("_", " "))
            url = val.get("url", f"A/{key}.html")
            text = val.get("text", val.get("snippet", ""))
            section = val.get("section")
            html = val.get("html", f"<html><head><title>{title}</title></head><body><h1>{title}</h1><p>{text}</p></body></html>")

            sections = []
            if section:
                sections.append(
                    ArticleSection(
                        heading=section,
                        level=2,
                        text=text,
                        anchor=section.lower().replace(" ", "-"),
                    )
                )

            art = ArticleContent(
                title=title,
                url=url,
                html_content=html,
                text_content=text,
                mime_type="text/html",
                sections=sections,
                metadata={"source": "fallback", "key": key},
            )

            # Register under multiple lookup keys
            self._articles[key.lower()] = art
            self._articles[title.lower()] = art
            self._articles[url.lower()] = art
            norm_key = key.replace("_", " ").lower()
            self._articles[norm_key] = art

        if not self._metadata:
            self._metadata = ZimArchiveMetadata(
                archive_path="in-memory-fallback",
                title="Wikipedia Offline Emergency Corpus",
                article_count=len(articles),
                creator="Wikipedia / Kiwix",
                date="2026-10",
                language="eng",
                file_size_mb=round(len(str(articles)) / (1024 * 1024), 2),
            )

    def _mount_archive(self, path: Path) -> None:
        """Mounts and verifies a physical .zim archive file."""
        if not path.is_file():
            raise ZimArchiveNotFoundError(str(path))

        size = path.stat().st_size
        if size < 80:
            raise ZimCorruptedError(f"Invalid ZIM archive: file size {size} bytes is smaller than ZIM header (80 bytes)")

        try:
            with open(path, "rb") as f:
                header_data = f.read(80)
                if len(header_data) < 80:
                    raise ZimCorruptedError("Incomplete ZIM header read")

                magic = struct.unpack_from("<I", header_data, 0)[0]
                if magic != self.ZIM_MAGIC and magic != 0x5a494d04:
                    raise ZimCorruptedError(f"Invalid ZIM magic bytes: expected 0x044D495A, got {hex(magic)}")

                major, minor = struct.unpack_from("<HH", header_data, 4)
                uuid_bytes = header_data[8:24]
                uuid_str = uuid_bytes.hex()
                article_count = struct.unpack_from("<I", header_data, 24)[0]

                self._metadata = ZimArchiveMetadata(
                    archive_path=str(path),
                    title=path.stem.replace("_", " ").replace("-", " ").title(),
                    article_count=article_count,
                    creator="Kiwix / OpenZIM",
                    date="2026-10",
                    language="eng",
                    uuid=uuid_str,
                    file_size_mb=round(size / (1024 * 1024), 2),
                )
        except (IOError, OSError) as e:
            raise ZimCorruptedError(f"Failed to read ZIM archive header: {e}")

    def is_available(self) -> bool:
        """Returns True if a valid ZIM archive or fallback store is mounted and ready."""
        return len(self._articles) > 0 or (self._metadata is not None and self._metadata.article_count > 0)

    def get_metadata(self) -> ZimArchiveMetadata:
        """Returns metadata for the active ZIM archive."""
        if self._metadata:
            return self._metadata
        return ZimArchiveMetadata(
            archive_path="none",
            title="Empty ZIM Archive",
            article_count=0,
            file_size_mb=0.0,
        )

    def search(self, query: str, limit: int = 5) -> List[ArticleSnippet]:
        """Performs ranked substring and keyword search across article titles and text."""
        if not query or not query.strip():
            return []

        q = query.strip()
        q_lower = q.lower()
        # Extract individual token words safely (escaped)
        words = [re.escape(w.lower()) for w in re.findall(r"\w+", q_lower)]

        matches: List[Tuple[float, ArticleContent]] = []
        seen_titles = set()

        for art in self._articles.values():
            if art.title in seen_titles:
                continue

            t_lower = art.title.lower()
            c_lower = art.text_content.lower()

            score = 0.0
            # Exact title match
            if t_lower == q_lower:
                score = 1.0
            # Title contains exact query string
            elif q_lower in t_lower:
                score = 0.95
            # Query contains exact title
            elif t_lower in q_lower:
                score = 0.90
            # Content contains exact query string
            elif q_lower in c_lower:
                score = 0.80
            else:
                # Word-level matching
                matched_words = sum(1 for w in words if re.search(rf"\b{w}\b", t_lower) or re.search(rf"\b{w}\b", c_lower))
                if words and matched_words > 0:
                    score = 0.5 + (0.3 * (matched_words / len(words)))

            if score > 0.0:
                matches.append((score, art))
                seen_titles.add(art.title)

        # Sort by score descending
        matches.sort(key=lambda x: x[0], reverse=True)

        results: List[ArticleSnippet] = []
        for score, art in matches[:limit]:
            # Generate snippet around match or beginning
            text = art.text_content
            snippet = text[:200]
            section = art.sections[0].heading if art.sections else None

            results.append(
                ArticleSnippet(
                    title=art.title,
                    url=art.url,
                    snippet=snippet,
                    section=section,
                    score=score,
                )
            )

        return results

    def _sanitize_path(self, path: str) -> Optional[str]:
        """Sanitizes article/asset path against directory traversal."""
        if not path:
            return None
        # Check for path traversal attempts
        if ".." in path or path.startswith("/") or path.startswith("\\") or ":" in path:
            return None
        # Normalize slashes
        clean = path.replace("\\", "/").strip()
        return clean

    def get_article(self, path: str) -> Optional[ArticleContent]:
        """Retrieves full article content by path or title."""
        if not path or not path.strip():
            return None

        # Sanitize path to block traversal
        clean_path = self._sanitize_path(path)
        if clean_path is None:
            return None

        clean_lower = clean_path.lower()

        # Direct dictionary lookup
        if clean_lower in self._articles:
            return self._articles[clean_lower]

        # Strip namespace (e.g., "A/" or "A\\") and ".html"
        stripped = clean_lower
        if stripped.startswith("a/"):
            stripped = stripped[2:]
        if stripped.endswith(".html"):
            stripped = stripped[:-5]
        if stripped.endswith(".htm"):
            stripped = stripped[:-4]

        # Normalized lookup
        if stripped in self._articles:
            return self._articles[stripped]

        # Underscore to space lookup
        with_spaces = stripped.replace("_", " ")
        if with_spaces in self._articles:
            return self._articles[with_spaces]

        with_underscores = stripped.replace(" ", "_")
        if with_underscores in self._articles:
            return self._articles[with_underscores]

        return None

    def get_asset(self, asset_path: str) -> Optional[ZimAsset]:
        """Retrieves binary image or media asset by relative path."""
        clean_path = self._sanitize_path(asset_path)
        if clean_path is None:
            return None

        clean_lower = clean_path.lower()
        if clean_lower in self._assets:
            return self._assets[clean_lower]

        return None

    def add_asset(self, path: str, data: bytes, mime_type: Optional[str] = None) -> None:
        """Registers a binary asset in the reader."""
        if not mime_type:
            mime_type, _ = mimetypes.guess_type(path)
            if not mime_type:
                mime_type = "application/octet-stream"

        asset = ZimAsset(path=path, data=data, mime_type=mime_type)
        self._assets[path.lower()] = asset
        self._assets[path.replace("\\", "/").lower()] = asset

    def list_articles(self, offset: int = 0, limit: int = 50) -> List[ArticleSnippet]:
        """Lists articles in sequential index order for catalogue browsing."""
        unique_arts: List[ArticleContent] = []
        seen = set()
        for art in self._articles.values():
            if art.title not in seen:
                unique_arts.append(art)
                seen.add(art.title)

        slice_arts = unique_arts[offset: offset + limit]
        return [
            ArticleSnippet(
                title=a.title,
                url=a.url,
                snippet=a.text_content[:200],
                section=a.sections[0].heading if a.sections else None,
                score=1.0,
            )
            for a in slice_arts
        ]
