from aibrother import (
    AI_BROTHER_CARD_SCHEMA_VERSION,
    CardWorkflow,
    ExperimentCard,
    MeetingCard,
    build_demo_cards,
    card_json_schema,
)
from aibrother.cards import CARD_LIBRARY_DIR


def test_starter_cards_cover_six_types() -> None:
    cards = build_demo_cards()

    assert AI_BROTHER_CARD_SCHEMA_VERSION == 1
    assert [card.type for card in cards] == [
        "ExperimentCard",
        "FailureCard",
        "IdeaCard",
        "MeetingCard",
        "PaperCard",
        "ReportCard",
    ]
    assert all(card.status == "draft" for card in cards)
    assert all(card.source == {} for card in cards)
    assert all(card.evidence == [] for card in cards)
    assert all(card.relations == [] for card in cards)
    assert all("template" in card.tags for card in cards)


def test_card_json_schema_exposes_base_and_type_fields() -> None:
    schema = card_json_schema("MeetingCard")

    required = set(schema["required"])
    assert {"id", "type", "title", "summary", "content", "tags"}.issubset(required)
    assert {"source", "status", "evidence", "relations"}.issubset(required)
    assert {"key_points", "decisions", "tasks", "questions"}.issubset(required)


def test_workflow_searches_generated_and_written_cards(tmp_path) -> None:
    workflow = CardWorkflow(tmp_path)
    card = workflow.generate(
        "ExperimentCard",
        title="CO2 absorption run",
        summary="Trial with solvent ratio changes",
        tags=["experiment", "co2"],
        objective="Compare absorption performance.",
        observations=["Foaming appeared after five minutes."],
        next_steps=["Repeat with lower stirring speed."],
    )

    assert isinstance(card, ExperimentCard)
    workflow.write(card)

    matches = workflow.search("foaming", card_type="ExperimentCard", tags=["co2"])
    assert [match.id for match in matches] == [card.id]
    assert workflow.read(card.id).objective == "Compare absorption performance."


def test_workflow_reads_nested_card_folders(tmp_path) -> None:
    workflow = CardWorkflow(tmp_path)
    card = workflow.generate(
        "IdeaCard",
        title="Nested idea",
        problem="Draft cards should stay searchable in nested writing folders.",
    )

    workflow.write(card, tmp_path / "drafts" / "idea" / "nested_idea.json")

    assert [match.id for match in workflow.search("nested writing folders")] == [card.id]


def test_default_library_writes_new_cards_to_drafts() -> None:
    workflow = CardWorkflow()
    card = workflow.generate("ReportCard", title="Draft report")

    path = workflow.write(card)
    try:
        assert path.parent == CARD_LIBRARY_DIR / "drafts"
    finally:
        path.unlink(missing_ok=True)


def test_workflow_validates_meeting_card_core_fields(tmp_path) -> None:
    workflow = CardWorkflow(tmp_path)
    card = workflow.generate(
        "MeetingCard",
        title="Group meeting",
        key_points=["Need a cleaner baseline."],
        decisions=["Run the baseline first."],
        tasks=[{"owner": "student", "task": "Prepare baseline report"}],
        questions=["Which metric should be primary?"],
    )

    assert isinstance(card, MeetingCard)
    assert card.key_points == ["Need a cleaner baseline."]
    assert workflow.write(card).name == f"{card.id}.json"
