from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select

from app.auth.service import create_user
from app.main import app
from app.models import AuthSession, ScheduleArchive, ScheduleMeeting, ScheduleSetting, ScheduleSubject, User
from app.services.schedule import content_without_ids

PASSWORD = 'synthetic schedule passphrase'


def meeting(weekday=0, start='08:00', end='09:30', **extra):
    return {'weekday': weekday, 'start': start, 'end': end, **extra}


def subject(name='Data Structures', meetings=None, **extra):
    return {'name': name, 'color': 'blue', 'meetings': [meeting()] if meetings is None else meetings, **extra}


def other_account(client, name='other_student'):
    with client.factory.begin() as db:
        user_id = create_user(db, f'{name}@example.com', PASSWORD, username=name).id
    browser = TestClient(app)
    response = browser.post('/api/auth/login', json={'email': f'{name}@example.com', 'password': PASSWORD})
    assert response.status_code == 200, response.text
    browser.headers['X-CSRF-Token'] = response.json()['csrf_token']
    return browser, user_id


def create(client, body):
    response = client.post('/api/schedule/subjects', json=body)
    assert response.status_code == 201, response.text
    return response.json()


def counts(client):
    with client.factory() as db:
        return (db.scalar(select(func.count()).select_from(ScheduleSubject)),
                db.scalar(select(func.count()).select_from(ScheduleMeeting)))


# CRUD and multiple meetings ---------------------------------------------------------------------

def test_one_subject_holds_several_meetings_with_optional_fields_and_room_overrides(client):
    saved = create(client, subject(code='  CS 201 ', instructor='', location='Room 301', color='mint', meetings=[
        meeting(2, '13:00', '15:00', location='Computer Lab'), meeting(0, '08:00', '09:30')]))
    assert saved['subject_id'] == saved['subjects'][0]['id'] and saved['conflicts'] == [] and saved['warnings'] == []
    view = client.get('/api/schedule').json()
    assert view['time_format'] == '12h' and len(view['subjects']) == 1
    item = view['subjects'][0]
    assert (item['name'], item['code'], item['instructor'], item['location'], item['color']) == \
        ('Data Structures', 'CS 201', None, 'Room 301', 'mint')  # blank optional fields are unset
    assert [(m['weekday'], m['start'], m['end'], m['location']) for m in item['meetings']] == [
        (0, '08:00', '09:30', None), (2, '13:00', '15:00', 'Computer Lab')]  # chronological; own room only when set
    assert counts(client) == (1, 2)


def test_editing_updates_kept_meetings_in_place_without_duplicating_the_subject(client):
    first = create(client, subject(meetings=[meeting(0), meeting(2, '13:00', '15:00'), meeting(4, '10:00', '11:00')]))
    item = first['subjects'][0]
    keep_monday, keep_wednesday, dropped_friday = item['meetings']
    body = subject('Data Structures II', color='lilac', code='CS 202', meetings=[
        {**meeting(0, '09:00', '10:30'), 'id': keep_monday['id']},          # time changed in place
        {**meeting(2, '13:00', '15:00', location='Lab 4'), 'id': keep_wednesday['id']},
        meeting(3, '14:00', '15:00'),                                       # new meeting
    ])                                                                       # Friday left out: removed
    response = client.put(f"/api/schedule/subjects/{item['id']}", json=body)
    assert response.status_code == 200, response.text
    updated = response.json()['subjects']
    assert len(updated) == 1 and counts(client) == (1, 3)
    assert (updated[0]['name'], updated[0]['color'], updated[0]['code']) == ('Data Structures II', 'lilac', 'CS 202')
    ids = [m['id'] for m in updated[0]['meetings']]
    assert keep_monday['id'] in ids and keep_wednesday['id'] in ids and dropped_friday['id'] not in ids
    assert [(m['weekday'], m['start']) for m in updated[0]['meetings']] == [(0, '09:00'), (2, '13:00'), (3, '14:00')]
    assert updated[0]['meetings'][1]['location'] == 'Lab 4'


def test_delete_removes_the_subject_and_all_its_meetings(client):
    saved = create(client, subject(meetings=[meeting(0), meeting(1), meeting(2)]))
    create(client, subject('Calculus', [meeting(0, '10:00', '11:00')]))
    response = client.delete(f"/api/schedule/subjects/{saved['subject_id']}")
    assert response.status_code == 200 and [s['name'] for s in response.json()['subjects']] == ['Calculus']
    assert counts(client) == (1, 1)
    assert client.delete(f"/api/schedule/subjects/{saved['subject_id']}").status_code == 404


# Validation ---------------------------------------------------------------------------------------

@pytest.mark.parametrize('payload', [
    subject(meetings=[meeting(start='09:30', end='08:00')]),             # end before start
    subject(meetings=[meeting(start='09:00', end='09:00')]),             # zero length
    subject(meetings=[meeting(start='23:00', end='01:00')]),             # overnight is not supported
    subject(meetings=[meeting(start='08:00', end='24:00')]),
    subject(meetings=[meeting(start='8:00', end='9:30')]),               # not normalized HH:MM
    subject(meetings=[meeting(start='08:00', end='09:60')]),
    subject(meetings=[meeting(start='08:00 AM', end='09:30 AM')]),       # display formats never reach the server
    subject(meetings=[meeting(weekday=7)]),
    subject(meetings=[meeting(weekday=-1)]),
    subject(meetings=[meeting(weekday='1')]),
    subject(meetings=[]),                                                 # at least one meeting
    subject(meetings=[meeting() for _ in range(15)]),                    # per-subject limit
    subject(name='   '), subject(name='x' * 81), subject(code='x' * 21), subject(instructor='x' * 81),
    subject(location='x' * 81), subject(meetings=[meeting(location='x' * 81)]),
    subject(color='neon'), subject(name='Bell\x07'), subject(extra_field=True),
    subject(meetings=[{**meeting(), 'unknown': 1}]),
    {'meetings': [meeting()]},
])
def test_invalid_subjects_are_rejected_and_nothing_is_saved(client, payload):
    assert client.post('/api/schedule/subjects', json=payload).status_code == 422
    assert counts(client) == (0, 0)


def test_midnight_and_noon_are_stored_as_normalized_minutes(client):
    create(client, subject(meetings=[meeting(0, '00:00', '00:30'), meeting(1, '12:00', '13:00'), meeting(2, '23:00', '23:59')]))
    with client.factory() as db:
        rows = [(m.weekday, m.start_minute, m.end_minute) for m in db.scalars(select(ScheduleMeeting).order_by(ScheduleMeeting.weekday))]
    assert rows == [(0, 0, 30), (1, 720, 780), (2, 1380, 1439)]


def test_invalid_updates_leave_the_existing_subject_untouched(client):
    saved = create(client, subject(meetings=[meeting(0), meeting(1)]))
    item = saved['subjects'][0]
    bad = subject('Renamed', meetings=[{**meeting(0), 'id': item['meetings'][0]['id']}, meeting(start='10:00', end='09:00')])
    assert client.put(f"/api/schedule/subjects/{item['id']}", json=bad).status_code == 422
    assert client.get('/api/schedule').json()['subjects'] == saved['subjects']


# Conflicts ----------------------------------------------------------------------------------------

def test_overlaps_are_reported_but_never_block_or_change_saves(client):
    create(client, subject('Calculus', [meeting(0, '10:00', '11:30')]))
    create(client, subject('Chemistry', [meeting(0, '11:30', '12:30'), meeting(1, '10:00', '11:00')]))  # touching ends
    assert client.get('/api/schedule').json()['conflicts'] == []
    saved = create(client, subject('Physics', [meeting(0, '11:00', '12:00'), meeting(1, '12:00', '13:00')]))
    names = sorted(tuple(sorted((c['a']['subject'], c['b']['subject']))) for c in saved['conflicts'])  # pair order follows start time
    assert names == [('Calculus', 'Physics'), ('Chemistry', 'Physics')]
    assert saved['warnings'] == saved['conflicts']  # both involve the saved subject
    assert counts(client) == (3, 5)  # saved despite the warning; nothing was removed or edited
    first = saved['conflicts'][0]
    assert first['weekday'] == 0 and {'subject_id', 'subject', 'meeting_id', 'start', 'end'} == set(first['a'])


def test_meetings_of_the_same_subject_can_conflict_and_other_days_do_not(client):
    saved = create(client, subject('Seminar', [meeting(0, '09:00', '10:00'), meeting(0, '09:30', '10:30'), meeting(1, '09:00', '10:00')]))
    assert len(saved['conflicts']) == 1 and saved['conflicts'][0]['weekday'] == 0
    assert saved['conflicts'][0]['a']['subject_id'] == saved['conflicts'][0]['b']['subject_id']


# Ownership and authentication -----------------------------------------------------------------------

def test_every_operation_is_scoped_to_the_signed_in_owner(client):
    mine = create(client, subject(meetings=[meeting(0), meeting(1)]))
    mine_id = mine['subject_id']
    other, _ = other_account(client)
    assert other.get('/api/schedule').json()['subjects'] == []
    assert other.put(f'/api/schedule/subjects/{mine_id}', json=subject('Stolen')).status_code == 404
    assert other.delete(f'/api/schedule/subjects/{mine_id}').status_code == 404
    theirs = create(other, subject('Theirs', [meeting(3)]))
    foreign_meeting = mine['subjects'][0]['meetings'][0]['id']
    stolen = subject('Theirs', [{**meeting(3), 'id': foreign_meeting}])  # another account's meeting id
    assert other.put(f"/api/schedule/subjects/{theirs['subject_id']}", json=stolen).status_code == 422
    assert client.get('/api/schedule').json()['subjects'] == mine['subjects']
    assert [s['name'] for s in other.get('/api/schedule').json()['subjects']] == ['Theirs']


def test_requests_require_authentication_and_csrf(client):
    saved = create(client, subject())
    subject_id = saved['subject_id']
    anonymous = TestClient(app)
    for method, path, body in (('get', '', None), ('delete', '', None), ('get', '/history', None),
                               ('get', '/history/1', None), ('post', '/history/1/restore', None),
                               ('post', '/subjects', subject()), ('put', f'/subjects/{subject_id}', subject()),
                               ('delete', f'/subjects/{subject_id}', None), ('put', '/preferences', {'time_format': '24h'})):
        assert getattr(anonymous, method)('/api/schedule' + path, **({'json': body} if body else {})).status_code == 401
    token = client.headers.pop('X-CSRF-Token')
    assert client.post('/api/schedule/subjects', json=subject('No token')).status_code == 403
    assert client.delete(f'/api/schedule/subjects/{subject_id}').status_code == 403
    assert client.delete('/api/schedule').status_code == 403
    assert client.post('/api/schedule/history/1/restore').status_code == 403
    client.headers['X-CSRF-Token'] = token
    assert counts(client) == (1, 1)


def test_deleting_an_account_removes_its_schedule(client):
    other, other_id = other_account(client)
    create(other, subject('Archived', meetings=[meeting(0), meeting(1)]))
    assert other.delete('/api/schedule').status_code == 200
    create(other, subject('Active', meetings=[meeting(0), meeting(1)]))
    other.put('/api/schedule/preferences', json={'time_format': '24h'})
    create(client, subject('Mine'))
    with client.factory.begin() as db:  # as the admin CLI does: sessions first, then the account
        db.execute(delete(AuthSession).where(AuthSession.user_id == other_id))
        db.execute(delete(User).where(User.id == other_id))
    assert counts(client) == (1, 1)
    with client.factory() as db:
        assert db.scalar(select(func.count()).select_from(ScheduleSetting).where(ScheduleSetting.user_id == other_id)) == 0
        assert db.scalar(select(func.count()).select_from(ScheduleArchive).where(ScheduleArchive.user_id == other_id)) == 0


# Schedule history ---------------------------------------------------------------------------------------

def test_clear_previews_and_restores_complete_schedules_without_losing_the_active_one(client):
    client.put('/api/schedule/preferences', json={'time_format': '24h'})
    create(client, subject('Physics', meetings=[meeting(0, '09:00', '10:00')]))
    original = create(client, subject(code='CS 201', instructor='Professor Lee', location='Room 2', color='lilac',
                                      meetings=[meeting(location='Lab'), meeting(6, '13:07', '15:00')]))
    cleared = client.delete('/api/schedule')
    assert cleared.status_code == 200 and cleared.json() == {'subjects': [], 'conflicts': [], 'time_format': '24h'}
    assert counts(client) == (0, 0)
    assert client.delete('/api/schedule').status_code == 200  # repeating a clear adds no empty archive
    entries = client.get('/api/schedule/history').json()['entries']
    assert len(entries) == 1 and entries[0]['subject_count'] == 2 and entries[0]['archived_at'].endswith('+00:00')
    path = f"/api/schedule/history/{entries[0]['id']}"
    assert client.get(path).json()['subjects'] == original['subjects']

    create(client, subject('Replacement'))
    restored = client.post(path + '/restore')
    assert restored.status_code == 200, restored.text
    restored_view = restored.json()
    assert restored_view['time_format'] == '24h' and len(restored_view['conflicts']) == 1
    assert content_without_ids(restored_view['subjects']) == content_without_ids(original['subjects'])
    assert restored_view['subjects'][0]['id'] != original['subjects'][0]['id']
    assert client.get(path).json()['subjects'] == original['subjects']  # immutable archive
    assert client.post(path + '/restore').json() == restored_view  # retry is a no-op
    after_restore = client.get('/api/schedule/history').json()['entries']
    assert len(after_restore) == 2 and after_restore[1] == entries[0]
    newest_path = f"/api/schedule/history/{after_restore[0]['id']}"
    assert client.post(newest_path + '/restore').json()['subjects'][0]['name'] == 'Replacement'


def test_history_keeps_the_latest_ten_for_each_account(client):
    other, _ = other_account(client)
    create(other, subject('Private class'))
    assert other.delete('/api/schedule').status_code == 200
    foreign = other.get('/api/schedule/history').json()['entries'][0]['id']
    assert client.get(f'/api/schedule/history/{foreign}').status_code == 404
    assert client.post(f'/api/schedule/history/{foreign}/restore').status_code == 404

    archive_ids = []
    for index in range(11):
        create(client, subject(f'Class {index}'))
        assert client.delete('/api/schedule').status_code == 200
        archive_ids.append(client.get('/api/schedule/history').json()['entries'][0]['id'])
    history = client.get('/api/schedule/history').json()
    assert history['limit'] == 10
    assert [entry['id'] for entry in history['entries']] == archive_ids[:0:-1]
    assert client.get(f'/api/schedule/history/{archive_ids[0]}').status_code == 404
    assert other.get('/api/schedule/history').json()['entries'][0]['id'] == foreign


def test_simultaneous_clears_save_one_snapshot(client):
    original = create(client, subject())
    with ThreadPoolExecutor(2) as pool:
        responses = list(pool.map(lambda _: client.delete('/api/schedule'), range(2)))
    assert all(response.status_code == 200 and not response.json()['subjects'] for response in responses)
    entries = client.get('/api/schedule/history').json()['entries']
    assert len(entries) == 1
    assert client.get(f"/api/schedule/history/{entries[0]['id']}").json()['subjects'] == original['subjects']


# Limits and concurrency -------------------------------------------------------------------------------

def test_subject_and_meeting_limits_are_enforced_per_account(client):
    for index in range(40):
        create(client, subject(f'Subject {index}'))
    refused = client.post('/api/schedule/subjects', json=subject('One too many'))
    assert refused.status_code == 409 and 'up to 40 subjects' in refused.json()['error']['message']
    other, _ = other_account(client)
    for index in range(14):  # 14 subjects x 14 meetings = 196 of the 200 allowed
        create(other, subject(f'Heavy {index}', [meeting(day % 7, f'{8 + day // 7}:00'.zfill(5), f'{8 + day // 7}:30'.zfill(5)) for day in range(14)]))
    assert other.post('/api/schedule/subjects', json=subject('Extra', [meeting(d, '18:00', '19:00') for d in range(5)])).status_code == 409
    assert other.post('/api/schedule/subjects', json=subject('Fits', [meeting(d, '18:00', '19:00') for d in range(4)])).status_code == 201


def test_simultaneous_creates_cannot_exceed_the_subject_limit(client):
    for index in range(38):
        create(client, subject(f'Subject {index}'))
    with ThreadPoolExecutor(8) as pool:
        codes = sorted(pool.map(lambda n: client.post('/api/schedule/subjects', json=subject(f'Race {n}')).status_code, range(8)))
    assert codes == [201, 201] + [409] * 6
    assert counts(client)[0] == 40


# Time format preference ---------------------------------------------------------------------------------

def test_time_format_preference_defaults_persists_and_is_per_account(client):
    assert client.get('/api/schedule').json()['time_format'] == '12h'
    assert client.put('/api/schedule/preferences', json={'time_format': '24h'}).json() == {'time_format': '24h'}
    assert client.get('/api/schedule').json()['time_format'] == '24h'
    fresh = TestClient(app)  # a new session for the same account keeps the preference
    login = fresh.post('/api/auth/login', json={'email': 'owner@example.com', 'password': 'correct horse battery staple'})
    assert login.status_code == 200
    assert fresh.get('/api/schedule').json()['time_format'] == '24h'
    other, _ = other_account(client)
    assert other.get('/api/schedule').json()['time_format'] == '12h'
    assert client.put('/api/schedule/preferences', json={'time_format': '12h'}).status_code == 200
    for bad in ({'time_format': 'AM'}, {'time_format': '24'}, {}, {'time_format': '24h', 'extra': 1}):
        assert client.put('/api/schedule/preferences', json=bad).status_code == 422
    with client.factory() as db:
        assert db.scalar(select(func.count()).select_from(ScheduleSetting)) == 1  # upsert, never a second row


# Migration ----------------------------------------------------------------------------------------------

@pytest.mark.parametrize('version', [6, 7])
def test_database_adds_schedule_history_without_touching_existing_data(tmp_path, version):
    from sqlalchemy.orm import Session
    from app.database import SCHEMA_VERSION, init_database, make_engine

    engine = make_engine(f"sqlite:///{(tmp_path / 'upgrade.db').as_posix()}")
    init_database(engine)
    with Session(engine) as db, db.begin():
        user = create_user(db, 'keeper@example.com', PASSWORD, username='keeper')
        db.flush()
        user_id = user.id
        if version == 7:
            item = ScheduleSubject(user_id=user_id, name='Keeper class')
            db.add(item)
            db.flush()
            db.add(ScheduleMeeting(subject_id=item.id, weekday=0, start_minute=480, end_minute=570))
    with engine.begin() as connection:
        connection.exec_driver_sql('DROP TABLE schedule_archives')
        if version == 6:
            for table in ('schedule_meetings', 'schedule_subjects', 'schedule_settings'):
                connection.exec_driver_sql(f'DROP TABLE {table}')
        connection.exec_driver_sql(f'PRAGMA user_version={version}')
    init_database(engine)
    with engine.connect() as connection:
        assert connection.exec_driver_sql('PRAGMA user_version').scalar_one() == SCHEMA_VERSION == 8
        tables = {row[0] for row in connection.exec_driver_sql("SELECT name FROM sqlite_schema WHERE type='table'")}
        assert {'schedule_subjects', 'schedule_meetings', 'schedule_settings', 'schedule_archives'} <= tables
        if version == 7:
            assert connection.exec_driver_sql('SELECT name FROM schedule_subjects').scalar_one() == 'Keeper class'
            assert connection.exec_driver_sql('SELECT start_minute FROM schedule_meetings').scalar_one() == 480
        assert connection.exec_driver_sql('SELECT username FROM users WHERE id = ?', (user_id,)).scalar_one() == 'keeper'
        assert connection.exec_driver_sql('PRAGMA foreign_key_check').all() == []
    assert len(list((tmp_path / '.migration-backups' / 'upgrade.db').glob('pre-migration-*.db'))) == 1
    engine.dispose()
