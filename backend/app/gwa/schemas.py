from decimal import Decimal
from typing import Literal

from pydantic import Field, field_validator

from app.schemas import InputModel


class CourseInput(InputModel):
    subject: str | None = Field(default=None, max_length=120)
    units: Decimal = Field(gt=0, max_digits=12, decimal_places=4, allow_inf_nan=False)
    grade: Decimal = Field(ge=1, le=5, max_digits=7, decimal_places=6, allow_inf_nan=False)

    @field_validator("units", "grade", mode="before")
    @classmethod
    def reject_boolean(cls, value):
        if isinstance(value, bool):
            raise ValueError("Enter a number, not a boolean.")
        return value

    @field_validator("subject")
    @classmethod
    def normalize_subject(cls, value):
        return value or None


class CalculationInput(InputModel):
    courses: list[CourseInput] = Field(min_length=1, max_length=15)


class CourseSummary(InputModel):
    subject: str | None
    units: float
    grade: float
    weighted_grade: float


class CalculationSummary(InputModel):
    courses: list[CourseSummary]
    course_count: int
    total_units: float
    total_weighted_grades: float
    gwa: float
    gwa_display: str
    percentage: float = Field(ge=0, le=100)
    classification: Literal["First Honor", "Second Honor", "Third Honor", "Passing", "Failed"]
    performance: Literal["Excellent", "Just passing", "Passing", "Failed"]
    honor: Literal["First Honor", "Second Honor", "Third Honor"] | None
    is_passing: bool
    honor_eligible: bool
    failed_course_count: int
