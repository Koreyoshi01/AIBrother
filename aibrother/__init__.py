"""AI Brother prototype layer."""

from __future__ import annotations

__all__ = [
    "AI_BROTHER_CARD_SCHEMA_VERSION",
    "AIBrotherCard",
    "AIBrotherCardKind",
    "AIBrotherRuntime",
    "BaseCard",
    "CardWorkflow",
    "ExperimentCard",
    "FailureCard",
    "IdeaCard",
    "MeetingCard",
    "PaperCard",
    "ReportCard",
    "build_demo_cards",
    "card_json_schema",
    "load_card",
    "parse_card",
    "write_card",
]

_LAZY_EXPORTS = {
    "AI_BROTHER_CARD_SCHEMA_VERSION": "aibrother.cards",
    "AIBrotherCard": "aibrother.cards",
    "AIBrotherCardKind": "aibrother.cards",
    "BaseCard": "aibrother.cards",
    "CardWorkflow": "aibrother.cards",
    "ExperimentCard": "aibrother.cards",
    "FailureCard": "aibrother.cards",
    "IdeaCard": "aibrother.cards",
    "MeetingCard": "aibrother.cards",
    "PaperCard": "aibrother.cards",
    "ReportCard": "aibrother.cards",
    "build_demo_cards": "aibrother.cards",
    "card_json_schema": "aibrother.cards",
    "load_card": "aibrother.cards",
    "parse_card": "aibrother.cards",
    "write_card": "aibrother.cards",
    "AIBrotherRuntime": "aibrother.runtime",
}


def __getattr__(name: str):
    module_name = _LAZY_EXPORTS.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    from importlib import import_module

    module = import_module(module_name)
    value = getattr(module, name)
    globals()[name] = value
    return value
