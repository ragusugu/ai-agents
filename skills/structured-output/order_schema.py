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
RequestKind = Literal[
    "return", "complaint", "order", "status", "quote", "availability", "delivery_cost", "other"
]
# First applicable request wins; request order breaks ties of the same kind.
REQUEST_PRIORITY = {
    kind: priority for priority, kind in enumerate(
        ("return", "complaint", "order", "status", "quote", "availability", "delivery_cost", "other")
    )
}


class EmailRequest(ExtractionModel):
    intent: Intent
    kind: RequestKind
    description: str

    @model_validator(mode="after")
    def check_intent(self) -> Self:
        expected = self.kind if self.kind in {"return", "complaint", "order", "status"} else "other"
        if self.intent != expected:
            raise ValueError(f"Request kind {self.kind!r} must use intent {expected!r}.")
        return self


class OrderRequest(ExtractionModel):
    customer: str | None = None
    contact: str | None = None
    intent: Intent
    primary_request: EmailRequest
    secondary_requests: list[EmailRequest]
    line_items: list[LineItem]
    requested_date: date | None = None
    urgency: Literal["low", "normal", "high", "urgent"] | None = None
    confidence: float = Field(ge=0, le=1)
    purchase_authorized: bool | None = None

    @model_validator(mode="after")
    def check_requests(self) -> Self:
        requests = [self.primary_request, *self.secondary_requests]
        if self.intent != self.primary_request.intent:
            raise ValueError("intent must equal primary_request.intent.")
        if any(REQUEST_PRIORITY[r.kind] < REQUEST_PRIORITY[self.primary_request.kind] for r in requests):
            raise ValueError("Choose primary request by return, complaint, order, status, quote, availability, delivery_cost, other priority.")
        identities = [(r.kind, " ".join(r.description.casefold().split())) for r in requests]
        if len(set(identities)) != len(identities):
            raise ValueError("Do not duplicate the same request in primary/secondary requests.")
        kinds = {r.kind for r in requests}
        if "order" in kinds and self.purchase_authorized is not True:
            raise ValueError("An order request requires explicit purchase authorization; quote-first requests are other.")
        if "quote" in kinds and "order" not in kinds and self.purchase_authorized is not False:
            raise ValueError("A quotation without a purchase instruction must have purchase_authorized=false.")
        return self


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
