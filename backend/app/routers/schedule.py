"""Authenticated class schedule CRUD. Subjects hold recurring weekly meetings, all owned by one user."""
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import Field, field_validator, model_validator
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.auth.dependencies import require_user
from app.database import get_db, get_write_db
from app.models import ScheduleArchive, ScheduleMeeting, ScheduleSetting, ScheduleSubject, User, utcnow
from app.schemas import InputModel
from app.services import schedule

router = APIRouter(prefix='/api/schedule', tags=['Class schedule'])

TIME = r'^([01]\d|2[0-3]):[0-5]\d$'  # Normalized 24-hour text; the display format never reaches the server.
Color = Literal['blue', 'mint', 'lilac', 'peach', 'rose', 'butter', 'sky', 'sage']


def plain_text(value):
    if value is not None and not value.isprintable():
        raise ValueError('Use plain text without control characters.')
    return value or None  # An empty optional field means "not set".


class MeetingInput(InputModel):
    id: int | None = Field(default=None, ge=1, strict=True)  # Present when keeping an existing meeting.
    weekday: int = Field(ge=0, le=6, strict=True)  # 0 = Monday … 6 = Sunday
    start: str = Field(pattern=TIME)
    end: str = Field(pattern=TIME)
    location: str | None = Field(default=None, max_length=80)
    _plain = field_validator('location')(plain_text)

    @model_validator(mode='after')
    def end_after_start(self):
        if schedule.to_minutes(self.end) <= schedule.to_minutes(self.start):
            raise ValueError('End time must be after start time. Overnight classes are not supported yet.')
        return self


class SubjectInput(InputModel):
    name: str = Field(min_length=1, max_length=80)
    code: str | None = Field(default=None, max_length=20)
    instructor: str | None = Field(default=None, max_length=80)
    location: str | None = Field(default=None, max_length=80)
    color: Color = 'blue'
    meetings: list[MeetingInput] = Field(min_length=1, max_length=schedule.MAX_MEETINGS_PER_SUBJECT)
    _plain = field_validator('name', 'code', 'instructor', 'location')(plain_text)


class PreferencesInput(InputModel):
    time_format: Literal['12h', '24h']


def owned_subject(db, user, subject_id):
    # The user filter is part of the lookup, so another account's subject is indistinguishable from a missing one.
    subject = db.scalar(select(ScheduleSubject).where(ScheduleSubject.id == subject_id, ScheduleSubject.user_id == user.id))
    if subject is None:
        raise HTTPException(404, 'Subject not found.')
    return subject


def saved(db, user, subject_id):
    view = schedule.snapshot(db, user.id)
    return {**view, 'subject_id': subject_id, 'warnings': schedule.warnings_for(view['conflicts'], subject_id)}


@router.get('')
def read_schedule(user: User = Depends(require_user), db: Session = Depends(get_db)):
    return schedule.snapshot(db, user.id)


@router.delete('')
def clear_schedule(user: User = Depends(require_user), db: Session = Depends(get_write_db, scope='function')):
    schedule.archive_and_clear(db, user.id, schedule.schedule_subjects(db, user.id))
    return schedule.snapshot(db, user.id)


@router.get('/history')
def read_history(user: User = Depends(require_user), db: Session = Depends(get_db)):
    return {'entries': schedule.history(db, user.id), 'limit': schedule.MAX_ARCHIVES}


def owned_archive(db, user_id, archive_id):
    archive = db.scalar(select(ScheduleArchive).where(ScheduleArchive.id == archive_id,
                                                      ScheduleArchive.user_id == user_id))
    if archive is None:
        raise HTTPException(404, 'Saved schedule not found.')
    return archive


@router.get('/history/{archive_id}')
def read_history_entry(archive_id: int, user: User = Depends(require_user), db: Session = Depends(get_db)):
    return {'subjects': owned_archive(db, user.id, archive_id).subjects}


@router.post('/history/{archive_id}/restore')
def restore_history_entry(archive_id: int, user: User = Depends(require_user),
                          db: Session = Depends(get_write_db, scope='function')):
    archive = owned_archive(db, user.id, archive_id)
    schedule.restore(db, user.id, archive.subjects)
    return schedule.snapshot(db, user.id)


@router.post('/subjects', status_code=201)
def create_subject(body: SubjectInput, user: User = Depends(require_user), db: Session = Depends(get_write_db, scope='function')):
    # Writers are serialized (BEGIN IMMEDIATE), so these limit checks cannot be raced past.
    if schedule.count_subjects(db, user.id) >= schedule.MAX_SUBJECTS:
        raise HTTPException(409, f'You can keep up to {schedule.MAX_SUBJECTS} subjects. Delete one to add another.')
    if schedule.count_meetings(db, user.id) + len(body.meetings) > schedule.MAX_MEETINGS:
        raise HTTPException(409, 'This would exceed the limit of meeting times for your schedule.')
    if any(meeting.id is not None for meeting in body.meetings):
        raise HTTPException(422, 'A new subject cannot reuse existing meetings.')
    subject = ScheduleSubject(user_id=user.id, name=body.name, code=body.code, instructor=body.instructor,
                              location=body.location, color=body.color)
    db.add(subject)
    db.flush()
    db.add_all(ScheduleMeeting(subject_id=subject.id, weekday=m.weekday, start_minute=schedule.to_minutes(m.start),
                               end_minute=schedule.to_minutes(m.end), location=m.location) for m in body.meetings)
    db.flush()
    return saved(db, user, subject.id)


@router.put('/subjects/{subject_id}')
def update_subject(subject_id: int, body: SubjectInput, user: User = Depends(require_user),
                   db: Session = Depends(get_write_db, scope='function')):
    """Replace a subject's details and meeting list in one transaction.

    Meetings sent with their id are updated in place, meetings without one are created, and meetings left
    out are removed, so editing one slot never duplicates the subject or its other slots.
    """
    subject = owned_subject(db, user, subject_id)
    existing = {m.id: m for m in db.scalars(select(ScheduleMeeting).where(ScheduleMeeting.subject_id == subject.id))}
    kept = [m.id for m in body.meetings if m.id is not None]
    if len(kept) != len(set(kept)) or any(meeting_id not in existing for meeting_id in kept):
        raise HTTPException(422, 'A meeting does not belong to this subject.')
    if schedule.count_meetings(db, user.id) - len(existing) + len(body.meetings) > schedule.MAX_MEETINGS:
        raise HTTPException(409, 'This would exceed the limit of meeting times for your schedule.')
    subject.name, subject.code, subject.instructor = body.name, body.code, body.instructor
    subject.location, subject.color, subject.updated_at = body.location, body.color, utcnow()
    for meeting in body.meetings:
        values = dict(weekday=meeting.weekday, start_minute=schedule.to_minutes(meeting.start),
                      end_minute=schedule.to_minutes(meeting.end), location=meeting.location)
        if meeting.id is None:
            db.add(ScheduleMeeting(subject_id=subject.id, **values))
        else:
            for key, value in values.items():
                setattr(existing[meeting.id], key, value)
    for meeting_id in set(existing) - set(kept):
        db.delete(existing[meeting_id])
    db.flush()
    return saved(db, user, subject.id)


@router.delete('/subjects/{subject_id}')
def delete_subject(subject_id: int, user: User = Depends(require_user), db: Session = Depends(get_write_db, scope='function')):
    subject = owned_subject(db, user, subject_id)
    db.execute(delete(ScheduleMeeting).where(ScheduleMeeting.subject_id == subject.id))
    db.delete(subject)
    db.flush()
    return schedule.snapshot(db, user.id)


@router.put('/preferences')
def update_preferences(body: PreferencesInput, user: User = Depends(require_user),
                       db: Session = Depends(get_write_db, scope='function')):
    setting = db.get(ScheduleSetting, user.id)
    if setting is None:
        db.add(ScheduleSetting(user_id=user.id, time_format=body.time_format))
    else:
        setting.time_format = body.time_format
    return {'time_format': body.time_format}
