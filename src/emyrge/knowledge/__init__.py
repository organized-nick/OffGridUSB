"""Offline Knowledge Core & Grounding Subsystem for Project eMyrge.

Exposes:
- F-09: Offline ZIM Reader (Native & fallback OpenZIM article extraction)
- F-10: Khan Academy Curriculum Engine (Structured topics, lessons & exercises)
- F-11: Knowledge Grounding Harness Mode (Active RAG, validated citations, audit pass)
- F-12: Non-Harness Direct Mode (AI-free direct encyclopedia & curriculum search)
"""

from .zim_reader import (
    ZimReader,
    ArticleSnippet,
    ArticleSection,
    ArticleContent,
    ZimAsset,
    ZimArchiveMetadata,
    ZimError,
    ZimArchiveNotFoundError,
    ZimCorruptedError,
    ZimArticleNotFoundError,
)

from .khan_curriculum import (
    KhanCurriculum,
    Exercise,
    Topic,
    LessonSnippet,
    LessonContent,
    ExerciseResult,
    CurriculumError,
    LessonNotFoundError,
    InvalidCurriculumDataError,
)

from .grounding_harness import (
    GroundingHarness,
    Citation,
    CitationType,
    HarnessMode,
    GroundedSource,
    GroundingContext,
    GroundedResponse,
    NonHarnessSearchResult,
    DirectContent,
    HarnessError,
    CitationFormatError,
)

__all__ = [
    # ZIM Reader (F-09)
    "ZimReader",
    "ArticleSnippet",
    "ArticleSection",
    "ArticleContent",
    "ZimAsset",
    "ZimArchiveMetadata",
    "ZimError",
    "ZimArchiveNotFoundError",
    "ZimCorruptedError",
    "ZimArticleNotFoundError",
    # Khan Curriculum (F-10)
    "KhanCurriculum",
    "Exercise",
    "Topic",
    "LessonSnippet",
    "LessonContent",
    "ExerciseResult",
    "CurriculumError",
    "LessonNotFoundError",
    "InvalidCurriculumDataError",
    # Grounding Harness & Direct Mode (F-11, F-12)
    "GroundingHarness",
    "Citation",
    "CitationType",
    "HarnessMode",
    "GroundedSource",
    "GroundingContext",
    "GroundedResponse",
    "NonHarnessSearchResult",
    "DirectContent",
    "HarnessError",
    "CitationFormatError",
]
