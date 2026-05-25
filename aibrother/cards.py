"""AI Brother card models and local JSON workflow.

This module is intentionally kept inside the ``aibrother`` package so the
project-specific card workflow can evolve without modifying upstream nanobot
runtime internals.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, TypeAdapter


AI_BROTHER_CARD_SCHEMA_VERSION = 1

CardType = Literal[
    "MeetingCard",
    "ExperimentCard",
    "PaperCard",
    "FailureCard",
    "IdeaCard",
    "ReportCard",
]
AIBrotherCardKind = CardType
CardStatus = Literal["draft", "ready", "active", "done", "blocked", "archived"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class BaseCard(StrictModel):
    id: str
    type: CardType
    title: str
    summary: str
    content: str
    tags: list[str]
    source: dict[str, Any]
    status: CardStatus
    evidence: list[dict[str, Any]]
    relations: list[dict[str, Any]]


class MeetingCard(BaseCard):
    type: Literal["MeetingCard"]
    key_points: list[str]
    decisions: list[str]
    tasks: list[dict[str, Any]]
    questions: list[str]


class ExperimentCard(BaseCard):
    type: Literal["ExperimentCard"]
    objective: str
    observations: list[str]
    problems: list[str]
    next_steps: list[str]


class PaperCard(BaseCard):
    type: Literal["PaperCard"]
    research_question: str
    method: str
    key_results: list[str]
    limitations: list[str]
    takeaways: list[str]


class FailureCard(BaseCard):
    type: Literal["FailureCard"]
    failure_event: str
    suspected_causes: list[str]
    fix_or_workaround: str
    lessons: list[str]


class IdeaCard(BaseCard):
    type: Literal["IdeaCard"]
    problem: str
    hypothesis: str
    proposed_method: str
    risks: list[str]
    validation_plan: list[str]


class ReportCard(BaseCard):
    type: Literal["ReportCard"]
    progress: list[str]
    problems: list[str]
    next_plan: list[str]
    slides_outline: list[str]


AIBrotherCard = (
    MeetingCard | ExperimentCard | PaperCard | FailureCard | IdeaCard | ReportCard
)
CARD_TYPE_MODELS: dict[str, type[BaseCard]] = {
    "MeetingCard": MeetingCard,
    "ExperimentCard": ExperimentCard,
    "PaperCard": PaperCard,
    "FailureCard": FailureCard,
    "IdeaCard": IdeaCard,
    "ReportCard": ReportCard,
}
_CARD_ADAPTER = TypeAdapter(AIBrotherCard)

CARD_LIBRARY_DIR = Path(__file__).with_name("card_library")
CARD_TEMPLATE_DIR = CARD_LIBRARY_DIR / "templates"
CARD_DRAFT_DIR = CARD_LIBRARY_DIR / "drafts"


def card_json_schema(card_type: CardType | None = None) -> dict[str, Any]:
    """Return the JSON Schema for all cards or one concrete card type."""

    if card_type is None:
        return _CARD_ADAPTER.json_schema()
    return CARD_TYPE_MODELS[card_type].model_json_schema()


def parse_card(data: dict[str, Any]) -> AIBrotherCard:
    """Validate raw JSON data and return the matching card model."""

    raw_type = data.get("type")
    if raw_type not in CARD_TYPE_MODELS:
        expected = ", ".join(CARD_TYPE_MODELS)
        raise ValueError(f"Unknown card type {raw_type!r}; expected one of: {expected}")
    return CARD_TYPE_MODELS[raw_type].model_validate(data)


def load_card(path: str | Path) -> AIBrotherCard:
    """Read and validate one card JSON file."""

    with Path(path).open("r", encoding="utf-8") as handle:
        return parse_card(json.load(handle))


def write_card(card: AIBrotherCard, path: str | Path) -> Path:
    """Write one validated card as stable, human-readable JSON."""

    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = card.model_dump(mode="json")
    with output_path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    return output_path


def build_demo_cards() -> list[AIBrotherCard]:
    """Load the six starter JSON cards shipped with AI Brother."""

    return CardWorkflow(CARD_TEMPLATE_DIR).read_all()


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower()).strip("-")
    return slug or "card"


def _defaults_for(card_type: CardType) -> dict[str, Any]:
    defaults: dict[str, dict[str, Any]] = {
        "MeetingCard": {
            "key_points": [],
            "decisions": [],
            "tasks": [],
            "questions": [],
        },
        "ExperimentCard": {
            "objective": "",
            "observations": [],
            "problems": [],
            "next_steps": [],
        },
        "PaperCard": {
            "research_question": "",
            "method": "",
            "key_results": [],
            "limitations": [],
            "takeaways": [],
        },
        "FailureCard": {
            "failure_event": "",
            "suspected_causes": [],
            "fix_or_workaround": "",
            "lessons": [],
        },
        "IdeaCard": {
            "problem": "",
            "hypothesis": "",
            "proposed_method": "",
            "risks": [],
            "validation_plan": [],
        },
        "ReportCard": {
            "progress": [],
            "problems": [],
            "next_plan": [],
            "slides_outline": [],
        },
    }
    return defaults[card_type].copy()


def _text_values(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        values: list[str] = []
        for item in value:
            values.extend(_text_values(item))
        return values
    if isinstance(value, dict):
        values = []
        for item in value.values():
            values.extend(_text_values(item))
        return values
    return []


class CardWorkflow:
    """Local JSON workflow for reading, searching, generating, and writing cards."""

    def __init__(self, root: str | Path = CARD_LIBRARY_DIR) -> None:
        self.root = Path(root)

    def paths(self) -> list[Path]:
        if not self.root.exists():
            return []
        return sorted(self.root.rglob("*.json"))

    def read_all(self) -> list[AIBrotherCard]:
        return [load_card(path) for path in self.paths()]

    def read(self, card_id: str) -> AIBrotherCard:
        for card in self.read_all():
            if card.id == card_id:
                return card
        raise FileNotFoundError(f"Card {card_id!r} was not found under {self.root}")

    def search(
        self,
        query: str = "",
        *,
        card_type: CardType | None = None,
        status: CardStatus | None = None,
        tags: list[str] | None = None,
    ) -> list[AIBrotherCard]:
        query_text = query.strip().lower()
        tag_filter = {tag.lower() for tag in tags or []}
        matches: list[AIBrotherCard] = []

        for card in self.read_all():
            if card_type is not None and card.type != card_type:
                continue
            if status is not None and card.status != status:
                continue
            card_tags = {tag.lower() for tag in card.tags}
            if tag_filter and not tag_filter.issubset(card_tags):
                continue
            if query_text and query_text not in self._search_blob(card):
                continue
            matches.append(card)

        return matches

    def generate(
        self,
        card_type: CardType,
        *,
        title: str,
        summary: str = "",
        content: str = "",
        tags: list[str] | None = None,
        source: dict[str, Any] | None = None,
        status: CardStatus = "draft",
        evidence: list[dict[str, Any]] | None = None,
        relations: list[dict[str, Any]] | None = None,
        card_id: str | None = None,
        **fields: Any,
    ) -> AIBrotherCard:
        payload = {
            "id": card_id or f"{_slugify(title)}-{uuid4().hex[:8]}",
            "type": card_type,
            "title": title,
            "summary": summary,
            "content": content,
            "tags": tags or [],
            "source": source or {},
            "status": status,
            "evidence": evidence or [],
            "relations": relations or [],
        }
        payload.update(_defaults_for(card_type))
        payload.update(fields)
        return parse_card(payload)

    def write(self, card: AIBrotherCard, path: str | Path | None = None) -> Path:
        if path is not None:
            output_path = Path(path)
        elif self.root == CARD_LIBRARY_DIR:
            output_path = CARD_DRAFT_DIR / f"{card.id}.json"
        else:
            output_path = self.root / f"{card.id}.json"
        return write_card(card, output_path)

    @staticmethod
    def _search_blob(card: AIBrotherCard) -> str:
        payload = card.model_dump(mode="json")
        return "\n".join(_text_values(payload)).lower()
