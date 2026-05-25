# AI Brother

`aibrother/` is the project-specific layer for AI Brother features. Keep
upstream `nanobot/` responsible for agent runtime, channels, tools, config, and
WebUI infrastructure. New AI Brother business logic should land here first, then
call nanobot through a small adapter only when runtime execution is needed.

## File Organization

```text
aibrother/
|-- card_library/                 # Card writing workspace
|   |-- templates/                 # Canonical blank JSON cards
|   |-- drafts/                    # Generated or manually edited drafts
|   `-- archive/                   # Stable completed cards
|-- knowledge/                     # Layered Markdown knowledge base
|   |-- lab_manual/                # Lab protocols and manuals
|   |-- group_knowledge/           # Group experiment records and Q&A history
|   |-- papers/                    # Paper summaries
|   `-- public/                    # Public links and external notes
|-- skills/ask_senior/SKILL.md     # AI Brother skill instructions
|-- memory/MEMORY.md               # Long-term memory
|-- config.json                    # Nanobot config placeholder
|-- demo.py                        # Scenario demo script
|-- cards.py                       # Card schema and JSON workflow
|-- runtime.py                     # Adapter boundary to nanobot
`-- README.md
```

## Card Workflow

The first card version uses a small required base shape:

```json
{
  "id": "",
  "type": "",
  "title": "",
  "summary": "",
  "content": "",
  "tags": [],
  "source": {},
  "status": "",
  "evidence": [],
  "relations": []
}
```

Six concrete card types add their own core fields:

- `MeetingCard`: `key_points`, `decisions`, `tasks`, `questions`
- `ExperimentCard`: `objective`, `observations`, `problems`, `next_steps`
- `PaperCard`: `research_question`, `method`, `key_results`, `limitations`, `takeaways`
- `FailureCard`: `failure_event`, `suspected_causes`, `fix_or_workaround`, `lessons`
- `IdeaCard`: `problem`, `hypothesis`, `proposed_method`, `risks`, `validation_plan`
- `ReportCard`: `progress`, `problems`, `next_plan`, `slides_outline`

Starter JSON files live in `aibrother/card_library/templates/`. Writing drafts
belong in `aibrother/card_library/drafts/`, and stable cards can move to
`aibrother/card_library/archive/`. The workflow reads the library recursively,
so templates, drafts, and archived cards remain searchable.

```python
from aibrother import CardWorkflow, build_demo_cards, card_json_schema

cards = build_demo_cards()
schema = card_json_schema("MeetingCard")

workflow = CardWorkflow()
card = workflow.generate(
    "ExperimentCard",
    title="CO2 absorption run",
    objective="Compare absorption performance.",
)
workflow.write(card)
matches = workflow.search("absorption", card_type="ExperimentCard")
```

When using the default `CardWorkflow()`, generated cards are written into
`aibrother/card_library/drafts/`.

## Knowledge Workflow

The current AI Brother demo uses a layered knowledge layout:

- `knowledge/lab_manual/`: lab manuals and operation protocols
- `knowledge/group_knowledge/`: group records, experiment history, and Q&A
- `knowledge/papers/`: paper summaries and reading notes
- `knowledge/public/`: public links and external knowledge

The agent can search these layers before falling back to public web search.

## Resource Import Workflow

Imported resources live under `knowledge/resources/` and are grouped by use
case:

- `group_meeting_ppt/`: generated Markdown summaries for group meeting slides
- `experiment_records/`: generated Markdown summaries for experiment records
- `read_papers/`: generated Markdown summaries for read papers
- `originals/`: copied source files, grouped by the same categories
- `RESOURCE_INDEX.md`: human-readable resource index
- `resources.jsonl`: structured resource index for WebUI and future RAG

Use `import_resource()` to copy a source file into `originals/`, extract text,
generate a conservative first-pass analysis, write a summary Markdown file, and
refresh both indexes:

```python
from aibrother import import_resource

record = import_resource(
    "path/to/paper.pdf",
    "read_papers",
    title="MEA-MDEA hybrid solvents",
    status="ready",
)
print(record.summary_md_path)
```

Supported categories are `group_meeting_ppt`, `experiment_records`, and
`read_papers`. The first-pass analysis extracts tags, key findings, a short
summary, and questions that still need manual confirmation. Later RAG indexing
should treat the original file as the source of truth and the generated
Markdown/JSONL files as rebuildable indexes.

Agent workflows can use the `resource_manager` skill plus
`aibrother_import_resource` for uploads and `aibrother_search_resources` before
falling back to the broader `knowledge/` tree or web search. These tools use
the same Markdown and JSONL indexes, so the frontend can read the resource
library without a separate ingestion path.

## Quick Start

```bash
cd AIBrother
pip install -e .
```

Set an API key through the environment or `aibrother/config.json`, then run:

```bash
PYTHONUTF8=1 python aibrother/demo.py
```

## Boundary

Keep business logic, writing artifacts, and lab-specific knowledge under
`aibrother/`. Keep upstream runtime changes inside `nanobot/` only when a real
runtime capability must be changed.
