from fastapi import APIRouter, Body, Depends
from sqlalchemy.orm import Session

from app.auth.dependencies import require_user
from app.database import get_db, get_write_db
from app.models import User
from app.schemas import InputModel
from app.services.activity import activity_view, mark_study_day

router = APIRouter(prefix='/api', tags=['Study activity'])


class CompletedPomodoro(InputModel):
    """No client-provided dates or ownership fields are accepted."""


@router.get('/dashboard/activity')
def get_activity(user: User = Depends(require_user), db: Session = Depends(get_db)):
    return activity_view(db, user)


@router.post('/activity/pomodoro')
def completed_pomodoro(payload: CompletedPomodoro = Body(default=CompletedPomodoro()),
                       user: User = Depends(require_user), db: Session = Depends(get_write_db, scope="function")):
    mark_study_day(db, user.id)
    return activity_view(db, user)
