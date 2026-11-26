"""Structured-output skill's schema template and local validation rules.

Edit this file to change the extraction contract. The native provider schema is
derived from these models; schema validity does not prove extraction accuracy.
"""

import re
from datetime import date
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ExtractionModel(BaseModel):
    """Strict types, no extra keys, no blank strings or non-finite numbers."""
    model_config = ConfigDict(
        strict=True,
        extra="forbid",
        str_strip_whitespace=True,
        str_min_length=1,
        allow_inf_nan=False,
    )


class LineItem(ExtractionModel):
    """A product mentioned in an email; unknown values remain None."""

    sku: str | None = None
    description: str | None = None
    quantity: Annotated[int, Field(gt=0)] | Annotated[float, Field(gt=0)] | None = None
    unit: str | None = None

    @model_validator(mode="after")
    def require_product_identity(self) -> Self:
        if self.sku is None and self.description is None:
            raise ValueError("Provide at least a SKU or a product description.")
        if self.sku is not None and re.fullmatch(r"MS-\d+", self.sku, flags=re.IGNORECASE):
            raise ValueError(
                "Order references (such as MS-10xxx) are not product SKUs; "
                "set sku to null or omit the line item when no product is named."
            )
        return self


Intent = Literal["order", "status", "complaint", "return", "other"]
INTENT_PRIORITY = ("return", "complaint", "order", "status", "other")


class OrderRequest(ExtractionModel):
    """Only the six requested fields; multi-intent resolves to one primary intent."""

    customer: str | None = None
    intent: Intent = Field(description=(
        "For multiple intents, return only the primary intent using this priority: "
        + ", ".join(INTENT_PRIORITY) + ". Quotes and stock/price enquiries use other. "
        "Order requires an explicit purchase instruction."
    ))
    line_items: list[LineItem]
    requested_date: date | None = None
    urgency: Literal["low", "normal", "high", "urgent"] | None = None
    confidence: float = Field(ge=0, le=1)


class FieldCheck(ExtractionModel):
    path: str
    verdict: Literal["supported", "unsupported", "uncertain"]
    source_quotes: list[str]
    explanation: str


class SourceCheck(ExtractionModel):
    segment: int
    verdict: Literal["covered", "not_material", "omitted", "uncertain"]
    candidate_paths: list[str]
    explanation: str


class GroundingReport(ExtractionModel):
    verdict: Literal["pass", "fail", "uncertain"]
    field_checks: list[FieldCheck]
    source_checks: list[SourceCheck]


def bedrock_schema(model=OrderRequest):
    """Derive the native schema; keep unsupported bounds in LOCAL validation.

    AWS supports a JSON Schema subset. Require all keys (unknown values can be
    null), prohibit extra keys, and retain types, enums, date formats and refs.
    Cross-field validators also remain local, so every response is revalidated.
    """
    local_only = {
        "minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum", "multipleOf",
        "minLength", "maxLength", "default",
    }

    def adapt(node):
        if isinstance(node, list):
            return [adapt(value) for value in node]
        if not isinstance(node, dict):
            return node
        result = {key: adapt(value) for key, value in node.items() if key not in local_only}
        if result.get("type") == "object":
            result["additionalProperties"] = False
            result["required"] = list(result.get("properties", {}))
        return result

    return adapt(model.model_json_schema())
