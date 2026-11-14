from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator
from app.services.card_images import MAX_IMAGE_DATA_URL_LENGTH, validate_card_image

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
    front_image: str | None = Field(default=None, max_length=MAX_IMAGE_DATA_URL_LENGTH)
    back_image: str | None = Field(default=None, max_length=MAX_IMAGE_DATA_URL_LENGTH)

    @field_validator("front_image", "back_image")
    @classmethod
    def valid_images(cls, value):
        return validate_card_image(value)


class CardPatch(InputModel):
    card_type: CardType | None = None
    front: str | None = Field(default=None, min_length=1, max_length=10000)
    back: str | None = Field(default=None, min_length=1, max_length=10000)
    front_image: str | None = Field(default=None, max_length=MAX_IMAGE_DATA_URL_LENGTH)
    back_image: str | None = Field(default=None, max_length=MAX_IMAGE_DATA_URL_LENGTH)

    @field_validator("front_image", "back_image")
    @classmethod
    def valid_images(cls, value):
        return validate_card_image(value)

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
