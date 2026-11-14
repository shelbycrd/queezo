import base64
from datetime import date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import func, inspect, select, text

from app.auth.service import create_user
from app.database import make_engine
from app.main import app
from app.media_migration import migrate_card_images
from app.models import ActivityDay, StudyReview, StudySessionCard
from app.schemas import CardInput
from app.services.card_images import MAX_IMAGE_BYTES
from conftest import deck, presentation, review

PNG = 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a9McAAAAASUVORK5CYII='


def test_image_survives_edits_and_snapshot_conceals_answer_media(client):
    identity = deck(client, 0)
    response = client.post(f'/api/decks/{identity}/cards', json={
        'front':'Question', 'back':'Answer', 'front_image':PNG, 'back_image':PNG})
    assert response.status_code == 201, response.text
    card = response.json()
    assert card['front_image'] == card['back_image'] == PNG
    # Omitted attachments survive text-only edits.
    edited = client.patch(f"/api/cards/{card['id']}", json={'front':'New question'}).json()
    assert edited['front_image'] == edited['back_image'] == PNG
    state = client.post(f'/api/decks/{identity}/study').json()
    assert state['current_card']['front_image'] == PNG
    assert 'back' not in state['current_card']
    assert 'back_image' not in state['current_card']
    # Explicit null removes current media without mutating the saved session.
    removed = client.patch(f"/api/cards/{card['id']}", json={'front_image':None,'back_image':None}).json()
    assert 'front_image' not in removed and 'back_image' not in removed
    assert client.delete(f"/api/cards/{card['id']}").status_code == 204
    revealed = client.post(f"/api/study/{state['id']}/reveal", json=presentation(state)).json()
    assert revealed['current_card']['front_image'] == PNG
    assert revealed['current_card']['back_image'] == PNG
    assert revealed['current_card']['back'] == 'Answer'


@pytest.mark.parametrize('value', [
    'https://example.com/photo.png',
    'data:image/svg+xml;base64,PHN2ZyBvbmxvYWQ9ImFsZXJ0KDEpIi8+',
    'data:text/html;base64,PGgxPkhlbGxvPC9oMT4=',
    'data:image/png;base64,!!!',
    'data:image/png;base64,SGVsbG8=',
    PNG.replace('image/png', 'image/jpeg'),
    PNG.replace('base64,', 'base64,\n'),
    'data:image/png;base64,' + base64.b64encode(b'x' * (MAX_IMAGE_BYTES + 1)).decode(),
])
def test_invalid_image_types_payloads_and_sizes_are_rejected(value):
    with pytest.raises(ValidationError):
        CardInput(front='Q', back='A', front_image=value)


def test_recent_cards_are_latest_first_limited_and_private(client):
    identity = deck(client, 3)
    original = client.get(f'/api/decks/{identity}/cards').json()
    result = client.get('/api/cards/recent?limit=2')
    assert result.status_code == 200, result.text
    assert [card['id'] for card in result.json()] == [card['id'] for card in original][-2:][::-1]
    assert all(card['deck_title'] == 'Operating Systems' for card in result.json())
    for limit in ['0', '31', 'abc']:
        assert client.get(f'/api/cards/recent?limit={limit}').status_code == 422
    with client.factory() as db:
        create_user(db, 'other.media@example.com', 'Different safe password 2026')
        db.commit()
    with TestClient(app) as other:
        user = other.post('/api/auth/login', json={
            'email':'other.media@example.com', 'password':'Different safe password 2026'}).json()
        other.headers['X-CSRF-Token'] = user['csrf_token']
        assert other.get('/api/cards/recent').json() == []
        assert other.patch(f"/api/cards/{original[0]['id']}", json={'front_image':PNG}).status_code == 404


def test_media_migration_is_additive_idempotent_and_preserves_old_content(tmp_path):
    engine = make_engine(f"sqlite:///{(tmp_path / 'old-media.db').as_posix()}")
    try:
        with engine.begin() as db:
            for table in ['flashcards','study_session_cards']:
                db.execute(text(f'CREATE TABLE {table} (id INTEGER PRIMARY KEY, front TEXT, back TEXT)'))
                db.execute(text(f"INSERT INTO {table} VALUES (1, 'Original question', 'Original answer')"))
            migrate_card_images(db)
            migrate_card_images(db)
            for table in ['flashcards','study_session_cards']:
                row = db.execute(text(f'SELECT * FROM {table}')).mappings().one()
                assert dict(row) == {'id':1, 'front':'Original question', 'back':'Original answer',
                                     'front_image':None, 'back_image':None}
                columns = inspect(db).get_columns(table)
                assert len(columns) == 5
    finally:
        engine.dispose()


@pytest.fixture
def activity_day(monkeypatch):
    # 16:30 UTC is already the following day in Manila.
    monkeypatch.setattr('app.services.activity.utcnow', lambda: datetime(2026,11,13,16,30))
    return date(2026,11,14)


def test_completed_pomodoro_marks_current_manila_day_once(client, activity_day):
    before = client.get('/api/dashboard/activity').json()
    assert before == {'study_streak':0, 'active_today':False, 'active_days':[],
                      'today':'2026-11-14','timezone':'Asia/Manila'}
    for _ in range(3):
        response = client.post('/api/activity/pomodoro', json={})
        assert response.status_code == 200, response.text
        assert response.json()['study_streak'] == 1
        assert response.json()['active_today'] is True
    with client.factory() as db:
        assert db.scalar(select(func.count()).select_from(ActivityDay)) == 1
        assert db.scalar(select(ActivityDay.day)) == activity_day
    assert client.post('/api/activity/pomodoro', json={'day':'2025-01-01'}).status_code == 422
    assert client.post('/api/activity/pomodoro', headers={'X-CSRF-Token':''}, json={}).status_code == 403


def test_streak_continues_yesterday_then_increments_today_and_respects_gaps(client, activity_day):
    with client.factory() as db:
        for delta in [1,2,3,5]:
            db.add(ActivityDay(user_id=client.test_user_id, day=activity_day-timedelta(days=delta)))
        db.commit()
    assert client.get('/api/dashboard/activity').json()['study_streak'] == 3
    result = client.post('/api/activity/pomodoro', json={}).json()
    assert result['study_streak'] == 4
    assert result['active_today'] is True


def test_old_or_other_account_activity_does_not_inflate_streak(client, activity_day):
    with client.factory() as db:
        other = create_user(db, 'activity.other@example.com', 'Another safe test password')
        db.add(ActivityDay(user_id=client.test_user_id, day=activity_day-timedelta(days=2)))
        for delta in [0,1,2]:
            db.add(ActivityDay(user_id=other.id, day=activity_day-timedelta(days=delta)))
        db.commit()
    result = client.get('/api/dashboard/activity').json()
    assert result['study_streak'] == 0
    assert result['active_today'] is False
    assert result['active_days'] == ['2026-11-12']


def test_card_review_marks_activity_but_reveal_does_not_and_deletion_keeps_day(client, activity_day):
    identity = deck(client)
    state = client.post(f'/api/decks/{identity}/study').json()
    client.post(f"/api/study/{state['id']}/reveal", json=presentation(state))
    assert client.get('/api/dashboard/activity').json()['active_today'] is False
    review(client, state)
    assert client.get('/api/dashboard/activity').json()['active_today'] is True
    assert client.delete(f'/api/decks/{identity}').status_code == 204
    assert client.get('/api/dashboard/activity').json()['study_streak'] == 1


def test_historical_reviews_join_owned_session_and_use_manila_midnight(client, activity_day):
    identity = deck(client)
    state = client.post(f'/api/decks/{identity}/study').json()
    state = review(client, state)
    with client.factory() as db:
        # Simulate a review predating the activity-day table and crossing local midnight.
        for row in db.scalars(select(ActivityDay)):
            db.delete(row)
        saved = db.scalar(select(StudyReview))
        saved.reviewed_at = datetime(2026,11,12,16,1)  # Manila November 13
        db.commit()
    result = client.get('/api/dashboard/activity').json()
    assert result['active_days'] == ['2026-11-13']
    assert result['study_streak'] == 1
    assert result['active_today'] is False


def test_new_media_and_activity_endpoints_require_login(anonymous_client):
    assert anonymous_client.get('/api/cards/recent').status_code == 401
    assert anonymous_client.get('/api/dashboard/activity').status_code == 401
    assert anonymous_client.post('/api/activity/pomodoro', json={}).status_code == 401
