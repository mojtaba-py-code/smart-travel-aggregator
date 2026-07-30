"""Money value object.

Money is stored and transported as an integer number of minor units (cents)
plus an ISO-4217 currency code. Floating point is never used for money.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

_ISO_4217_LEN = 3


class Money(BaseModel):
    model_config = {"frozen": True}

    amount_minor: int = Field(ge=0, description="Amount in minor units, e.g. cents.")
    currency: str = Field(min_length=_ISO_4217_LEN, max_length=_ISO_4217_LEN)

    @field_validator("currency")
    @classmethod
    def _upper_currency(cls, value: str) -> str:
        if not value.isalpha():
            raise ValueError("currency must be a 3-letter ISO-4217 code")
        return value.upper()

    @property
    def as_decimal(self) -> float:
        """Convenience for display only — never use for arithmetic on money."""
        return self.amount_minor / 100

    def __str__(self) -> str:
        return f"{self.as_decimal:.2f} {self.currency}"
