"""Class schedule views and overlap detection. Every query is scoped to the owning user."""
from datetime import timezone

from sqlalchemy import delete, func, select

from app.models import ScheduleArchive, ScheduleMeeting, ScheduleSetting, ScheduleSubject

COLORS = ('blue', 'mint', 'lilac', 'peach', 'rose', 'butter', 'sky', 'sage')
TIME_FORMATS = ('12h', '24h')
DEFAULT_FORMAT = '12h'
MAX_SUBJECTS = 40
MAX_MEETINGS_PER_SUBJECT = 14
MAX_MEETINGS = 200  # Per user across all subjects.
MAX_CONFLICTS = 50  # A worst-case schedule cannot produce an unbounded response.
MAX_ARCHIVES = 10


def to_minutes(text):
    hours, minutes = text.split(':')
    return int(hours) * 60 + int(minutes)


def to_text(minutes):
    return f'{minutes // 60:02d}:{minutes % 60:02d}'


def meeting_view(meeting):
    return {'id': meeting.id, 'weekday': meeting.weekday, 'start': to_text(meeting.start_minute),
            'end': to_text(meeting.end_minute), 'location': meeting.location}


def subject_view(subject, meetings):
    return {'id': subject.id, 'name': subject.name, 'code': subject.code, 'instructor': subject.instructor,
            'location': subject.location, 'color': subject.color, 'meetings': [meeting_view(m) for m in meetings]}


def time_format(db, user_id):
    return db.scalar(select(ScheduleSetting.time_format).where(ScheduleSetting.user_id == user_id)) or DEFAULT_FORMAT


def find_conflicts(subjects):
    """Pairs of meetings on one weekday whose times overlap. Touching ends (9:30 and 9:30) do not."""
    by_day = {}
    for subject in subjects:
        for meeting in subject['meetings']:
            by_day.setdefault(meeting['weekday'], []).append((to_minutes(meeting['start']), to_minutes(meeting['end']),
                                                              subject, meeting))
    found = []
    for weekday in sorted(by_day):
        slots = sorted(by_day[weekday], key=lambda slot: (slot[0], slot[1], slot[3]['id']))
        for index, (start, end, subject, meeting) in enumerate(slots):
            for other_start, other_end, other, other_meeting in slots[index + 1:]:
                if other_start >= end:
                    break  # Sorted by start, so nothing later can overlap this slot.
                found.append({'weekday': weekday,
                              'a': {'subject_id': subject['id'], 'subject': subject['name'], 'meeting_id': meeting['id'],
                                    'start': meeting['start'], 'end': meeting['end']},
                              'b': {'subject_id': other['id'], 'subject': other['name'], 'meeting_id': other_meeting['id'],
                                    'start': other_meeting['start'], 'end': other_meeting['end']}})
                if len(found) >= MAX_CONFLICTS:
                    return found
    return found


def schedule_subjects(db, user_id):
    subjects = list(db.scalars(select(ScheduleSubject).where(ScheduleSubject.user_id == user_id)
                               .order_by(func.lower(ScheduleSubject.name), ScheduleSubject.id)))
    grouped = {}
    for meeting in db.scalars(select(ScheduleMeeting).join(ScheduleSubject, ScheduleSubject.id == ScheduleMeeting.subject_id)
                              .where(ScheduleSubject.user_id == user_id)
                              .order_by(ScheduleMeeting.weekday, ScheduleMeeting.start_minute, ScheduleMeeting.end_minute,
                                        ScheduleMeeting.id)):
        grouped.setdefault(meeting.subject_id, []).append(meeting)
    return [subject_view(subject, grouped.get(subject.id, [])) for subject in subjects]


def snapshot(db, user_id):
    views = schedule_subjects(db, user_id)
    return {'time_format': time_format(db, user_id), 'subjects': views, 'conflicts': find_conflicts(views)}


def history(db, user_id):
    entries = db.execute(
        select(ScheduleArchive.id, ScheduleArchive.archived_at, func.json_array_length(ScheduleArchive.subjects))
        .where(ScheduleArchive.user_id == user_id)
        .order_by(ScheduleArchive.id.desc())
    )
    return [{'id': archive_id, 'archived_at': stamp.replace(tzinfo=timezone.utc).isoformat(), 'subject_count': count}
            for archive_id, stamp, count in entries]


def archive_and_clear(db, user_id, subjects):
    if not subjects:
        return
    db.add(ScheduleArchive(user_id=user_id, subjects=subjects))
    db.flush()
    latest = (select(ScheduleArchive.id).where(ScheduleArchive.user_id == user_id)
              .order_by(ScheduleArchive.id.desc()).limit(MAX_ARCHIVES))
    db.execute(delete(ScheduleArchive).where(ScheduleArchive.user_id == user_id, ScheduleArchive.id.not_in(latest)))
    # The foreign key cascades to meetings, in the same transaction as creating the archive.
    db.execute(delete(ScheduleSubject).where(ScheduleSubject.user_id == user_id))


def content_without_ids(subjects):
    return [{**{key: value for key, value in subject.items() if key not in ('id', 'meetings')},
             'meetings': [{key: value for key, value in meeting.items() if key != 'id'}
                          for meeting in subject['meetings']]} for subject in subjects]


def restore(db, user_id, archived_subjects):
    current = schedule_subjects(db, user_id)
    # Repeating a restore of the active schedule should never add a history entry.
    if content_without_ids(current) == content_without_ids(archived_subjects):
        return
    archive_and_clear(db, user_id, current)
    for item in archived_subjects:
        subject = ScheduleSubject(user_id=user_id, name=item['name'], code=item['code'],
                                  instructor=item['instructor'], location=item['location'], color=item['color'])
        db.add(subject)
        db.flush()
        db.add_all(ScheduleMeeting(subject_id=subject.id, weekday=m['weekday'], start_minute=to_minutes(m['start']),
                                   end_minute=to_minutes(m['end']), location=m['location']) for m in item['meetings'])
    db.flush()


def count_subjects(db, user_id):
    return db.scalar(select(func.count()).select_from(ScheduleSubject).where(ScheduleSubject.user_id == user_id))


def count_meetings(db, user_id):
    return db.scalar(select(func.count()).select_from(ScheduleMeeting)
                     .join(ScheduleSubject, ScheduleSubject.id == ScheduleMeeting.subject_id)
                     .where(ScheduleSubject.user_id == user_id))


def warnings_for(conflicts, subject_id):
    return [item for item in conflicts if subject_id in (item['a']['subject_id'], item['b']['subject_id'])]
