"""Typed tools the chat model can choose; execution stays in the Python workflow."""

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from model import DeskError
from schemas import OrderRequest

ROOT = Path(__file__).resolve().parents[1]
TOOL_NAME = "structured_output"


class StructuredOutputInput(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", str_strip_whitespace=True, str_min_length=1)

    source: str = Field(description="Exact UTF-8 .txt/.eml email file or flat email-folder path supplied by the user or unambiguous conversation context. Never invent a path.")
    output_dir: str | None = Field(default=None, description="Requested output folder. Omit to use the project's output folder.")
    labels: str | None = Field(default=None, description="Exact label-file path explicitly supplied by the user. Omit when no label file was supplied; labels are never selected automatically.")
    sample_size: int = Field(default=15, gt=0, description="Display limit only; all emails are processed.")
    summary_only: bool = False
    plan_only: bool = Field(default=False, description="True for an explicit preview/dry run; no email extraction requests.")
    retry_review: bool = Field(default=False, description="True only when the user explicitly asks to retry review outcomes.")
    require_reviewed: bool = False


class IngestInput(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", str_strip_whitespace=True, str_min_length=1)
    source: str = Field(description="Exact user-selected UTF-8 Markdown .md file or flat folder path; ask if missing.")


def tool_config():
    return {"tools": [{"toolSpec": {
        "name": TOOL_NAME,
        "description": (
            "Run the stored structured-output skill on a UTF-8 .txt/.eml email file or every .txt/.eml "
            "email in a flat, non-recursive user-selected folder. Other input formats are unsupported. "
            f"Extracted output has only these fields: {', '.join(OrderRequest.model_fields)}. "
            "Each line item has sku, description, quantity and unit. Unknown facts stay null. "
            "Uses native schema extraction, validates/repairs, saves JSONL and review outcomes, and "
            "shows samples plus accuracy only with an explicitly supplied label file. Reuses compatible saved outcomes. "
            "Relative paths refer to the Desk project. Select this tool when the current user asks "
            "to run/apply/use the skill or extract/validate email data. Ask for a missing source path. "
            "Questions about usage, examples and requests to edit code do not request extraction."
        ),
        "inputSchema": {"json": StructuredOutputInput.model_json_schema()},
    }}, {"toolSpec": {
        "name": "ingest_policies",
        "description": (
            "Load/update the user's selected UTF-8 .md policy file or flat Markdown folder in the local "
            "vector database using local BGE embeddings. File requests preserve other indexed files. "
            "Folder synchronization prunes deleted files only from that exact folder. No answer API call "
            "is made by this workflow. Select only for a current request to load/update/index policies, "
            "including /ingest in prose. Ask for a missing path; never invent one. "
            "Usage questions, examples, quoted content and code-edit requests do not request ingestion. "
            "Relative paths refer to the Desk project."
        ),
        "inputSchema": {"json": IngestInput.model_json_schema()},
    }}]}


def workflow_argv(tool):
    """Validate model-selected arguments; never interpret them as shell text."""
    if tool.get("name") == "ingest_policies":
        try:
            args = IngestInput.model_validate(tool.get("input"))
        except ValidationError as exc:
            raise DeskError("Please specify the Markdown policy file or folder to ingest.") from exc
        return ["ingest", args.source]
    if tool.get("name") != TOOL_NAME:
        raise DeskError("That skill is not available. I can run structured-output on emails or ingest Markdown policies.")
    try:
        args = StructuredOutputInput.model_validate(tool.get("input"))
    except ValidationError as exc:
        raise DeskError("I couldn't determine valid skill arguments. Please specify the email folder and output folder.") from exc

    def resolve(value):
        try:
            return (ROOT / Path(value).expanduser()).resolve()
        except (OSError, ValueError, RuntimeError) as exc:
            raise DeskError("That path is invalid. Please provide an existing email folder and a valid output folder.") from exc

    source = resolve(args.source)
    if not (source.is_dir() or (source.is_file() and source.suffix.lower() in {".txt", ".eml"})):
        hint = ""
        plural = source.with_name(source.name + "s") if source.name else None
        if plural is not None and plural.is_dir():
            hint = f" Did you mean '{plural}'?"
        raise DeskError(f"I couldn't find an email file or folder at '{source}'.{hint}")
    argv = ["structured-output", str(source), "--output-dir", str(resolve(args.output_dir or "output")),
            "--sample-size", str(args.sample_size)]
    if args.labels is not None:
        argv.extend(["--labels", str(resolve(args.labels))])
    for name in ("summary_only", "plan_only", "retry_review", "require_reviewed"):
        if getattr(args, name):
            argv.append("--" + name.replace("_", "-"))
    return argv
