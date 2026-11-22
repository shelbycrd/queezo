from contextlib import asynccontextmanager
import logging

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.concurrency import run_in_threadpool

from app.database import get_db, init_database
from app.errors import validation_error
from app.routers import activity, decks, friends, multiple_choice, profiles, study
from app.routers import community
from app.auth.router import router as auth_router
from app.auth.config import get_settings
from app.auth.middleware import PrivateResponseHeaders
from app.services.multiple_choice import PreparationJobs, recover_interrupted


@asynccontextmanager
async def lifespan(application):
    get_settings()
    init_database()
    await run_in_threadpool(recover_interrupted)
    jobs = PreparationJobs()
    application.state.multiple_choice_jobs = jobs
    try:
        yield
    finally:
        await jobs.stop()


app = FastAPI(title="Queezo App 1: Flashcards API", version="1.1.0", lifespan=lifespan)
app.include_router(decks.router)
app.include_router(study.router)
app.include_router(multiple_choice.router)
app.include_router(activity.router)
app.include_router(auth_router)
app.include_router(community.router)
app.include_router(friends.router)
app.include_router(profiles.router)
app.add_middleware(PrivateResponseHeaders)


@app.exception_handler(StarletteHTTPException)
async def http_error(_, exc):
    return JSONResponse(status_code=exc.status_code, content={"error": {"message": str(exc.detail)}}, headers=exc.headers)


app.add_exception_handler(RequestValidationError, validation_error)


@app.exception_handler(IntegrityError)
async def conflict(_, exc):
    return JSONResponse(status_code=409, content={"error": {"message": "This change conflicts with the current data. Refresh and try again."}})


@app.exception_handler(OperationalError)
async def unavailable(_, exc):
    logging.exception("Database operation failed", exc_info=exc)
    return JSONResponse(status_code=503, content={"error": {"message": "The database is temporarily unavailable. Try again shortly."}})


@app.exception_handler(Exception)
async def unexpected_error(request: Request, exc):
    logging.exception("Unhandled request error", exc_info=exc)
    return JSONResponse(status_code=500, content={"error": {"message": "An unexpected server error occurred."}})


@app.get("/api/health", tags=["Health"])
def health(db: Session = Depends(get_db)):
    db.execute(text("SELECT 1"))
    return {"status": "ok"}
