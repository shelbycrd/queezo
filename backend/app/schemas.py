from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

CardType = Literal["two_sided"]
Difficulty = Literal["easy", "normal", "hard"]


class InputModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class DeckInput(InputModel):
    title: str = Field(min_length=1, max_length=120)


class CardInput(InputModel):
    card_type: CardType = "two_sided"
    front: str = Field(min_length=1, max_length=10000)
    back: str = Field(min_length=1, max_length=10000)


class CardPatch(InputModel):
    card_type: CardType | None = None
    front: str | None = Field(default=None, min_length=1, max_length=10000)
    back: str | None = Field(default=None, min_length=1, max_length=10000)

    @field_validator("card_type", "front", "back")
    @classmethod
    def reject_null(cls, value):
        if value is None:
            raise ValueError("This field cannot be null.")
        return value


class PresentationInput(InputModel):
    presentation_number: int = Field(ge=1, strict=True)
    presentation_token: str = Field(min_length=36, max_length=36)


class RatingInput(PresentationInput):
    difficulty: Difficulty
