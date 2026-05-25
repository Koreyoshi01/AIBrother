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
    "RESOURCE_CATEGORY_LABELS",
    "RESOURCE_INDEX_JSONL",
    "RESOURCE_INDEX_MD",
    "RESOURCE_LIBRARY_DIR",
    "ResourceRecord",
    "build_demo_cards",
    "card_json_schema",
    "ensure_resource_library",
    "import_resource",
    "read_resource_records",
    "rebuild_resource_index_md",
    "load_card",
    "parse_card",
    "write_resource_records",
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
    "RESOURCE_CATEGORY_LABELS": "aibrother.resources",
    "RESOURCE_INDEX_JSONL": "aibrother.resources",
    "RESOURCE_INDEX_MD": "aibrother.resources",
    "RESOURCE_LIBRARY_DIR": "aibrother.resources",
    "ResourceRecord": "aibrother.resources",
    "build_demo_cards": "aibrother.cards",
    "card_json_schema": "aibrother.cards",
    "ensure_resource_library": "aibrother.resources",
    "import_resource": "aibrother.resources",
    "read_resource_records": "aibrother.resources",
    "rebuild_resource_index_md": "aibrother.resources",
    "load_card": "aibrother.cards",
    "parse_card": "aibrother.cards",
    "write_resource_records": "aibrother.resources",
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
