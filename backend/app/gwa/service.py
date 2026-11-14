"""Weighted GWA and user-defined classifications; no persistence or HTTP logic."""
from decimal import Decimal, ROUND_HALF_UP, localcontext

from app.gwa.schemas import CalculationInput, CalculationSummary, CourseSummary

HONOR_BANDS = (
    (Decimal("1.25"), "First Honor"),
    (Decimal("1.50"), "Second Honor"),
    (Decimal("1.75"), "Third Honor"),
)


def calculate(data: CalculationInput) -> CalculationSummary:
    # Bounded inputs need at most 21 significant digits for weighted totals.
    # Extra precision avoids binary-float artifacts at honor boundaries.
    with localcontext() as context:
        context.prec = 50
        total_units = sum((course.units for course in data.courses), Decimal(0))
        weighted_total = sum((course.grade * course.units for course in data.courses), Decimal(0))
        gwa = weighted_total / total_units
        honor = next((name for cutoff, name in HONOR_BANDS
                      if weighted_total <= cutoff * total_units), None)
        is_passing = weighted_total <= Decimal("3.00") * total_units
        if weighted_total == total_units:
            performance = "Excellent"
        elif weighted_total == 3 * total_units:
            performance = "Just passing"
        else:
            performance = "Passing" if is_passing else "Failed"
        displayed = gwa.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        percentage = ((Decimal(5) - gwa) * 25).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        return CalculationSummary(
            courses=[CourseSummary(subject=course.subject, units=float(course.units),
                     grade=float(course.grade), weighted_grade=float(course.units * course.grade))
                     for course in data.courses],
            course_count=len(data.courses), total_units=float(total_units),
            total_weighted_grades=float(weighted_total), gwa=float(displayed),
            gwa_display=f"{displayed:.2f}", percentage=float(percentage),
            classification=honor or ("Passing" if is_passing else "Failed"), honor=honor,
            performance=performance,
            is_passing=is_passing, honor_eligible=honor is not None,
            failed_course_count=sum(course.grade > 3 for course in data.courses),
        )
