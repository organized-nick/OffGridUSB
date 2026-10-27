"""Khan Academy Structured Curriculum Engine (F-10).

Zero-install, offline curriculum indexer for STEM & K-12 subjects, topics,
lessons, and interactive practice exercises stored in SQLite or JSON datasets.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
import re
import sqlite3
from typing import Any, Dict, List, Optional, Tuple, Union

from emyrge.core.config import EmyrgeError


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class CurriculumError(EmyrgeError):
    """Base exception for Khan Academy curriculum operations."""
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__("ERR_CURRICULUM_GENERAL", message, details)


class LessonNotFoundError(CurriculumError):
    """Raised when a requested lesson_id does not exist."""
    def __init__(self, lesson_id: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(f"Curriculum lesson not found: {lesson_id}", details or {"lesson_id": lesson_id})
        self.code = "ERR_LESSON_NOT_FOUND"


class InvalidCurriculumDataError(CurriculumError):
    """Raised when loaded curriculum dataset lacks required fields or valid schema."""
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message, details)
        self.code = "ERR_CURRICULUM_DATA_INVALID"


# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------

@dataclass
class Exercise:
    """Interactive practice exercise attached to a curriculum lesson."""
    id: str
    question: str
    answer: str
    hints: List[str] = field(default_factory=list)
    explanation: Optional[str] = None

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
            "id": self.id,
            "question": self.question,
            "answer": self.answer,
            "hints": self.hints,
            "explanation": self.explanation,
        }


@dataclass
class Topic:
    """Topic cluster within a broad subject domain."""
    subject: str
    name: str
    lesson_count: int = 0
    description: Optional[str] = None

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
            "subject": self.subject,
            "name": self.name,
            "lesson_count": self.lesson_count,
            "description": self.description,
        }


@dataclass
class LessonSnippet:
    """Compact summary of a curriculum lesson for search and indexing."""
    lesson_id: str
    subject: str
    topic: str
    title: str
    snippet: str

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
            "lesson_id": self.lesson_id,
            "subject": self.subject,
            "topic": self.topic,
            "title": self.title,
            "snippet": self.snippet,
        }


@dataclass
class LessonContent:
    """Full curriculum lesson content with interactive exercises."""
    lesson_id: str
    subject: str
    topic: str
    title: str
    content: str
    exercises: List[Exercise] = field(default_factory=list)
    prerequisites: List[str] = field(default_factory=list)

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
            "lesson_id": self.lesson_id,
            "subject": self.subject,
            "topic": self.topic,
            "title": self.title,
            "content": self.content,
            "exercises": [e.to_dict() for e in self.exercises],
            "prerequisites": self.prerequisites,
        }


@dataclass
class ExerciseResult:
    """Evaluation result from submitting an exercise answer."""
    exercise_id: str
    is_correct: bool
    user_answer: str
    expected_answer: str
    feedback: str

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
            "exercise_id": self.exercise_id,
            "is_correct": self.is_correct,
            "user_answer": self.user_answer,
            "expected_answer": self.expected_answer,
            "feedback": self.feedback,
        }


# ---------------------------------------------------------------------------
# KhanCurriculum Implementation
# ---------------------------------------------------------------------------

class KhanCurriculum:
    """Offline structured Khan Academy curriculum engine."""

    def __init__(
        self,
        db_path: Optional[str | Path] = None,
        fallback_lessons: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        self.db_path: Optional[Path] = Path(db_path) if db_path else None
        self._lessons: Dict[str, LessonContent] = {}

        if fallback_lessons is not None:
            self.load_curriculum(fallback_lessons)
        elif self.db_path and self.db_path.is_file():
            self._load_from_sqlite(self.db_path)

    def load_curriculum(self, data: Union[List[Dict[str, Any]], str, Path]) -> int:
        """Loads curriculum dataset from in-memory list or JSON/SQLite file."""
        if isinstance(data, (str, Path)):
            path = Path(data)
            if path.is_file():
                if path.suffix.lower() in (".db", ".sqlite", ".sqlite3"):
                    return self._load_from_sqlite(path)
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            else:
                # Attempt to parse as raw JSON string
                try:
                    data = json.loads(str(data))
                except Exception as e:
                    raise InvalidCurriculumDataError(f"Failed to parse curriculum JSON: {e}")

        if not isinstance(data, list):
            raise InvalidCurriculumDataError("Curriculum data must be a list of lesson records")

        count = 0
        for entry in data:
            if not isinstance(entry, dict):
                raise InvalidCurriculumDataError(f"Invalid lesson entry type: {type(entry)}")

            # Validate required fields
            for req in ("subject", "topic", "lesson_id", "title", "content"):
                if req not in entry:
                    raise InvalidCurriculumDataError(f"Missing required curriculum field '{req}' in {entry}")

            exercises_raw = entry.get("exercises", [])
            exercises: List[Exercise] = []
            for ex in exercises_raw:
                if isinstance(ex, dict):
                    exercises.append(
                        Exercise(
                            id=ex.get("id", f"ex-{len(exercises)+1}"),
                            question=ex.get("question", ""),
                            answer=ex.get("answer", ""),
                            hints=ex.get("hints", []),
                            explanation=ex.get("explanation"),
                        )
                    )
                elif isinstance(ex, Exercise):
                    exercises.append(ex)

            lesson = LessonContent(
                lesson_id=entry["lesson_id"],
                subject=entry["subject"],
                topic=entry["topic"],
                title=entry["title"],
                content=entry["content"],
                exercises=exercises,
                prerequisites=entry.get("prerequisites", []),
            )

            self._lessons[lesson.lesson_id] = lesson
            count += 1

        return count

    def _load_from_sqlite(self, path: Path) -> int:
        """Loads curriculum from SQLite database tables."""
        conn = sqlite3.connect(str(path))
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        count = 0
        try:
            # Check if lessons table exists
            cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='lessons'")
            if not cur.fetchone():
                return 0

            cur.execute("SELECT * FROM lessons")
            for row in cur.fetchall():
                lesson_id = row["lesson_id"]
                subject = row["subject"]
                topic = row["topic"]
                title = row["title"]
                content = row["content"]

                # Fetch attached exercises if table exists
                exercises = []
                cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='exercises'")
                if cur.fetchone():
                    cur.execute("SELECT * FROM exercises WHERE lesson_id = ?", (lesson_id,))
                    for ex_row in cur.fetchall():
                        hints = json.loads(ex_row["hints"]) if "hints" in ex_row.keys() and ex_row["hints"] else []
                        exercises.append(
                            Exercise(
                                id=ex_row["id"],
                                question=ex_row["question"],
                                answer=ex_row["answer"],
                                hints=hints,
                                explanation=ex_row["explanation"] if "explanation" in ex_row.keys() else None,
                            )
                        )

                lesson = LessonContent(
                    lesson_id=lesson_id,
                    subject=subject,
                    topic=topic,
                    title=title,
                    content=content,
                    exercises=exercises,
                )
                self._lessons[lesson.lesson_id] = lesson
                count += 1
        finally:
            conn.close()

        return count

    def get_subjects(self) -> List[str]:
        """Returns list of all distinct subject domains sorted alphabetically."""
        subjects = {lesson.subject for lesson in self._lessons.values()}
        return sorted(list(subjects))

    def get_topics(self, subject: Optional[str] = None) -> List[Topic]:
        """Returns topics under a specific subject, or all topics across all subjects."""
        topic_map: Dict[Tuple[str, str], int] = {}

        for lesson in self._lessons.values():
            if subject and lesson.subject.lower() != subject.lower():
                continue
            key = (lesson.subject, lesson.topic)
            topic_map[key] = topic_map.get(key, 0) + 1

        topics: List[Topic] = []
        for (subj, name), count in topic_map.items():
            topics.append(
                Topic(
                    subject=subj,
                    name=name,
                    lesson_count=count,
                    description=f"{subj} topic: {name}",
                )
            )

        topics.sort(key=lambda t: (t.subject, t.name))
        return topics

    def get_lessons_by_topic(self, topic: str, subject: Optional[str] = None) -> List[LessonSnippet]:
        """Returns all lesson summaries filed under a given topic."""
        snippets: List[LessonSnippet] = []
        t_lower = topic.strip().lower()

        for lesson in self._lessons.values():
            if lesson.topic.lower() == t_lower:
                if subject and lesson.subject.lower() != subject.lower():
                    continue
                snippets.append(
                    LessonSnippet(
                        lesson_id=lesson.lesson_id,
                        subject=lesson.subject,
                        topic=lesson.topic,
                        title=lesson.title,
                        snippet=lesson.content[:200],
                    )
                )

        return snippets

    def get_lesson(self, lesson_id: str) -> Optional[LessonContent]:
        """Retrieves full lesson content and attached exercises by lesson_id."""
        return self._lessons.get(lesson_id)

    def search(self, query: str, limit: int = 5) -> List[LessonSnippet]:
        """Searches curriculum lessons by title, topic, subject, or content text."""
        if not query or not query.strip():
            return []

        q_lower = query.strip().lower()
        words = [re.escape(w.lower()) for w in re.findall(r"\w+", q_lower)]

        matches: List[Tuple[float, LessonContent]] = []

        for lesson in self._lessons.values():
            score = 0.0
            t_lower = lesson.title.lower()
            top_lower = lesson.topic.lower()
            subj_lower = lesson.subject.lower()
            c_lower = lesson.content.lower()

            if t_lower == q_lower:
                score = 1.0
            elif q_lower in t_lower:
                score = 0.95
            elif q_lower in top_lower:
                score = 0.90
            elif q_lower in subj_lower:
                score = 0.85
            elif q_lower in c_lower:
                score = 0.80
            else:
                matched_words = sum(1 for w in words if re.search(rf"\b{w}\b", t_lower) or re.search(rf"\b{w}\b", c_lower))
                if words and matched_words > 0:
                    score = 0.5 + (0.3 * (matched_words / len(words)))

            if score > 0.0:
                matches.append((score, lesson))

        matches.sort(key=lambda x: x[0], reverse=True)

        return [
            LessonSnippet(
                lesson_id=lesson.lesson_id,
                subject=lesson.subject,
                topic=lesson.topic,
                title=lesson.title,
                snippet=lesson.content[:200],
            )
            for _, lesson in matches[:limit]
        ]

    def get_exercise(self, lesson_id: str, exercise_id: str) -> Optional[Exercise]:
        """Retrieves a specific exercise attached to a lesson."""
        lesson = self.get_lesson(lesson_id)
        if not lesson:
            return None
        for ex in lesson.exercises:
            if ex.id == exercise_id:
                return ex
        return None

    def evaluate_exercise(self, lesson_id: str, exercise_id: str, user_answer: str) -> ExerciseResult:
        """Evaluates user's answer against expected solution using trimmed, case-insensitive logic."""
        ex = self.get_exercise(lesson_id, exercise_id)
        if not ex:
            raise LessonNotFoundError(f"{lesson_id}:{exercise_id}")

        norm_user = user_answer.strip().lower()
        norm_expected = ex.answer.strip().lower()

        # Handle numeric / unit normalization: e.g. "3 amperes" vs "3 a" or "3"
        is_correct = (norm_user == norm_expected)
        if not is_correct:
            # Check numerical equivalence if both parse as numbers
            try:
                # Extract first float from both strings
                u_nums = re.findall(r"[-+]?\d*\.\d+|\d+", norm_user)
                e_nums = re.findall(r"[-+]?\d*\.\d+|\d+", norm_expected)
                if u_nums and e_nums and float(u_nums[0]) == float(e_nums[0]):
                    is_correct = True
            except ValueError:
                pass

        feedback = "Correct! Well done." if is_correct else f"Incorrect. Expected: {ex.answer}"
        return ExerciseResult(
            exercise_id=exercise_id,
            is_correct=is_correct,
            user_answer=user_answer,
            expected_answer=ex.answer,
            feedback=feedback,
        )
