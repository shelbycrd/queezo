from fastapi import Depends, FastAPI
from fastapi.exceptions import RequestValidationError

from app.errors import validation_error
from app.gwa.schemas import CalculationInput, CalculationSummary
from app.gwa.service import calculate
from app.auth.dependencies import require_user
from app.auth.config import get_settings
from app.auth.middleware import PrivateResponseHeaders
from app.models import User
from contextlib import asynccontextmanager


@asynccontextmanager
async def lifespan(_):
    get_settings()
    yield

app = FastAPI(title="Queezo App 2: GWA Calculator API", version="1.0.0", lifespan=lifespan,
              docs_url="/gwa/docs", redoc_url="/gwa/redoc", openapi_url="/gwa/openapi.json")
app.add_exception_handler(RequestValidationError, validation_error)
app.add_middleware(PrivateResponseHeaders)


@app.get("/api/gwa/health", tags=["Health"])
def health():
    return {"status": "ok"}


@app.post("/api/gwa/calculate", response_model=CalculationSummary, tags=["GWA"])
def calculate_gwa(data: CalculationInput, user: User = Depends(require_user)):
    """Calculate 1–15 courses. Honors use unrounded GWA; 1.25/1.50 favor the higher honor.

    Percentage is a linear visualization: (5 - GWA) / 4 * 100, not a school grade conversion.
    These classifications follow the configured project rules, not an institution's full policy.
    """
    return calculate(data)
