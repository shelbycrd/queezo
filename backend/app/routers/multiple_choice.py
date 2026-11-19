from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.auth.dependencies import require_user
from app.database import get_db, get_write_db
from app.models import User
from app.schemas import MultipleChoiceAnswer, MultipleChoiceTiming
from app.services import multiple_choice as study

router = APIRouter(prefix="/api", tags=["Multiple-choice study"])


@router.post("/decks/{deck_id}/multiple-choice", status_code=202)
async def start(deck_id: int, request: Request, user: User = Depends(require_user),
                timing: MultipleChoiceTiming | None = None):
    state, attempt = await run_in_threadpool(study.create_session, deck_id, user.id, timing)
    request.app.state.multiple_choice_jobs.start(state["id"], attempt)
    return state


@router.get("/decks/{deck_id}/multiple-choice/sessions")
def history(deck_id: int, user: User = Depends(require_user), db: Session = Depends(get_db)):
    return study.history(db, deck_id, user.id)


@router.get("/multiple-choice/{session_id}")
def status(session_id: str, user: User = Depends(require_user), db: Session = Depends(get_db)):
    return study.session_view(db, study.owned_session(db, session_id, user.id))


@router.post("/multiple-choice/{session_id}/start")
def begin_study(session_id: str, user: User = Depends(require_user)):
    return study.begin_study(session_id, user.id)


@router.post("/multiple-choice/{session_id}/retry", status_code=202)
async def retry(session_id: str, request: Request, user: User = Depends(require_user)):
    state, attempt = await run_in_threadpool(study.retry_session, session_id, user.id)
    request.app.state.multiple_choice_jobs.start(session_id, attempt)
    return state


@router.post("/multiple-choice/{session_id}/continue")
def continue_ready(session_id: str, user: User = Depends(require_user), db: Session = Depends(get_write_db)):
    return study.continue_session(db, study.owned_session(db, session_id, user.id))


@router.post("/multiple-choice/{session_id}/cancel")
async def cancel(session_id: str, request: Request, user: User = Depends(require_user)):
    state = await run_in_threadpool(study.cancel_session, session_id, user.id)
    await request.app.state.multiple_choice_jobs.cancel(session_id)
    return state


@router.get("/multiple-choice/{session_id}/question")
def question(session_id: str, user: User = Depends(require_user), db: Session = Depends(get_db)):
    return study.question_view(db, study.owned_session(db, session_id, user.id))


@router.post("/multiple-choice/{session_id}/question")
async def open_question(session_id: str, request: Request, user: User = Depends(require_user)):
    result = await run_in_threadpool(study.open_owned_question, session_id, user.id)
    if result["session"]["preparing"] and result["session"].get("deck_time_over"):
        # Let the current job exit and settle before returning a completed timed session.
        await request.app.state.multiple_choice_jobs.cancel(session_id)
        result = await run_in_threadpool(study.open_owned_question, session_id, user.id, True)
    return result


@router.post("/multiple-choice/{session_id}/answer")
def answer(session_id: str, submission: MultipleChoiceAnswer, user: User = Depends(require_user),
           db: Session = Depends(get_write_db)):
    return study.submit_answer(db, study.owned_session(db, session_id, user.id), submission)
