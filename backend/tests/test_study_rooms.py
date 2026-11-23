from fastapi.testclient import TestClient
from sqlalchemy import select

from app.auth.service import create_user
from app.main import app
from app.models import Friendship, RoomQuestion, RoomSession
from conftest import deck

PASSWORD = 'synthetic room passphrase'


def make_users(client, names, friendships=()):
    with client.factory.begin() as db:
        ids = {name: create_user(db, f'{name}@example.com', PASSWORD, username=name).id for name in names}
        for first, second in friendships:
            pair = sorted((ids[first], ids[second]))
            db.add(Friendship(first_id=pair[0], second_id=pair[1], requester_id=pair[0], accepted=True))
    return ids


def sign_in(name):
    browser = TestClient(app)
    response = browser.post('/api/auth/login', json={'email':f'{name}@example.com', 'password':PASSWORD})
    assert response.status_code == 200, response.text
    browser.headers['x-csrf-token'] = response.json()['csrf_token']
    return browser


def make_room(host, guest='bob'):
    response = host.post('/api/rooms', json={'username':guest})
    assert response.status_code == 201, response.text
    return '/api/rooms/' + response.json()['id']


def join(browser, path):
    return browser.post(path + '/invitation', json={'accept':True})


def test_private_lobby_readiness_and_deck_authorization(anonymous_client):
    make_users(anonymous_client, ('alice','bob','carol'), [('alice','bob')])
    alice, bob, carol = map(sign_in, ('alice','bob','carol'))
    path = make_room(alice)
    deck_id = deck(alice,3)
    other_deck = deck(carol)
    settings = {'deck_id':deck_id,'mode':'collaborative','share_private':True}
    assert bob.get('/api/rooms').json()['invites'][0]['sender']['username'] == 'alice'
    assert carol.get(path).status_code == 404
    assert join(carol,path).status_code == 404
    assert join(bob,path).status_code == join(bob,path).status_code == 204
    assert bob.patch(path + '/settings',json=settings).status_code == 403
    assert alice.patch(path + '/settings',json={**settings,'deck_id':other_deck}).status_code == 404
    assert alice.patch(path + '/settings',json={**settings,'share_private':False}).status_code == 422
    assert alice.patch(path + '/settings',json=settings).status_code == 204
    assert bob.post(path + '/ready',json={'ready':True}).status_code == 204
    assert alice.patch(path + '/settings',json={**settings,'mode':'challenge'}).status_code == 204
    assert alice.post(path + '/start').status_code == 409
    assert bob.post(path + '/ready',json={'ready':True}).status_code == 204
    assert bob.post(path + '/start').status_code == 403
    assert alice.post(path + '/start').status_code == 204
    assert bob.get(path).json()['phase'] == 'preparing'
    with anonymous_client.factory() as db:
        session = db.scalar(select(RoomSession))
        questions = list(db.scalars(select(RoomQuestion).order_by(RoomQuestion.position)))
        assert [question.position for question in questions] == list(range(3))
        assert len({question.card_id for question in questions}) == 3
        assert session.mode == 'challenge'


def test_friend_of_friend_invites_are_unique_and_enforce_capacity(anonymous_client):
    names = ('alice','bob','carol','david','elsie','frank','grace')
    make_users(anonymous_client, names, [('alice','bob'), *(('bob',name) for name in names[2:])])
    browsers = {name:sign_in(name) for name in names}
    alice, bob = browsers['alice'], browsers['bob']
    path = make_room(alice)
    assert join(bob,path).status_code == 204
    assert alice.post(path + '/invite',json={'username':'carol'}).status_code == 404
    for name in names[2:]:
        assert bob.post(path + '/invite',json={'username':name}).status_code == 204
        assert bob.post(path + '/invite',json={'username':name}).status_code == 204
        assert len(browsers[name].get('/api/rooms').json()['invites']) == 1
    for name in names[2:-1]:
        assert join(browsers[name],path).status_code == 204
    assert join(browsers['grace'],path).status_code == 409
    assert len(alice.get(path).json()['participants']) == 6


def configure_room(alice, bob, path, deck_id, mode='collaborative'):
    assert join(bob,path).status_code == 204
    assert alice.patch(path + '/settings', json={'deck_id':deck_id,'mode':mode,'share_private':True}).status_code == 204
    assert bob.post(path + '/ready', json={'ready':True}).status_code == 204
    assert alice.post(path + '/start').status_code == 204


def wait_for_state(browser, path, phase):
    import time

    stop = time.monotonic() + 12
    while time.monotonic() < stop:
        response = browser.get(path)
        assert response.status_code == 200
        view = response.json()
        if view['phase'] == phase:
            return view
        time.sleep(.06)
    raise AssertionError(f'Room did not reach {phase}: {view["phase"]}')


def answer_for(view, option_id):
    return {'session_id':view['session']['id'],'position':view['session']['position'],'option_id':option_id}


def test_collaborative_reveal_and_reconnect(anonymous_client, monkeypatch):
    from starlette.websockets import WebSocketDisconnect
    import pytest

    from app.auth.config import get_settings
    from app.services import room_study

    order = []
    async def generate(card_id, user, **kwargs):
        order.append(card_id)
        return ['Distractor one','Distractor two','Distractor three']
    monkeypatch.setattr(room_study, 'get_or_generate_distractors', generate)

    make_users(anonymous_client, ('alice','bob','carol'), [('alice','bob'),('alice','carol')])
    alice, bob, carol = map(sign_in, ('alice','bob','carol'))
    path = make_room(alice)
    configure_room(alice,bob,path,deck(alice,3))
    original = wait_for_state(alice,path,'question')
    with anonymous_client.factory() as db:
        assert order == list(db.scalars(select(RoomQuestion.card_id).order_by(RoomQuestion.position)))

    for browser, origin in ((carol,'http://testserver'), (alice,'https://invalid.example')):
        with pytest.raises(WebSocketDisconnect), browser.websocket_connect(path + '/live',headers={'origin':origin}):
            pass

    headers = {'origin':'http://testserver', 'cookie':get_settings().cookie_name + '=' + alice.cookies[get_settings().cookie_name]}
    with anonymous_client.websocket_connect(path + '/live',headers=headers) as live:
        state = live.receive_json()
        assert state['question']['options'] == original['question']['options']
        assert 'correct_id' not in state['question']
        assert 'back_image' not in state['question']
    assert alice.post(path + '/invite',json={'username':'carol'}).status_code == 204
    assert join(carol,path).status_code == 204
    opts = original['question']['options']
    assert carol.post(path + '/answer',json=answer_for(original,opts[0]['id'])).status_code == 403
    assert alice.post(path + '/answer',json=answer_for(original,opts[0]['id'])).status_code == 204
    assert alice.post(path + '/answer',json=answer_for(original,opts[1]['id'])).status_code == 409
    other_view = bob.get(path).json()
    assert other_view['question']['selected_id'] is None
    assert other_view['participants'][0]['answered']
    assert 'responses' not in other_view['question']
    assert alice.get(path).json()['question']['selected_id'] == opts[0]['id']
    assert bob.post(path + '/answer',json=answer_for(original,opts[1]['id'])).status_code == 204
    result = wait_for_state(bob,path,'reveal')
    assert result['question']['correct_id'] in {option['id'] for option in opts}
    assert len(result['question']['responses']) == 2
    assert alice.post(path + '/pause',json={'paused':True}).status_code == 204
    assert wait_for_state(bob,path,'reveal')['session']['paused']
    assert bob.post(path + '/pause',json={'paused':False}).status_code == 403
    assert alice.post(path + '/pause',json={'paused':False}).status_code == 204


def test_challenge_timer_clamps_late_answers_and_ranks_by_points(anonymous_client, monkeypatch):
    from datetime import datetime, timedelta

    from app.models import utcnow
    from app.services import room_study
    from app.services.presenters import iso

    async def generate(*args, **kwargs):
        return ['Distractor one','Distractor two','Distractor three']
    monkeypatch.setattr(room_study, 'get_or_generate_distractors', generate)
    make_users(anonymous_client, ('alice','bob'), [('alice','bob')])
    alice, bob = map(sign_in, ('alice','bob'))
    path = make_room(alice)
    configure_room(alice,bob,path,deck(alice),mode='challenge')
    view = wait_for_state(alice,path,'question')
    with anonymous_client.factory() as db:
        session = db.get(RoomSession,view['session']['id'])
        question = db.get(RoomQuestion,(session.id,0))
        assert (session.deadline - session.opened_at).total_seconds() == 30
        correct_id = question.correct_id
    assert alice.post(path + '/answer',json=answer_for(view,correct_id)).status_code == 204
    with anonymous_client.factory.begin() as db:
        db.get(RoomSession,view['session']['id']).deadline = utcnow() - timedelta(seconds=1)
    assert bob.post(path + '/answer',json=answer_for(view,correct_id)).status_code == 409
    revealed = wait_for_state(alice,path,'reveal')
    assert [entry['username'] for entry in revealed['leaderboard']] == ['alice','bob']
    assert 100 <= revealed['leaderboard'][0]['score'] <= 1000
    assert revealed['leaderboard'][1]['score'] == 0
    with anonymous_client.factory.begin() as db:
        db.get(RoomSession,view['session']['id']).deadline = utcnow() - timedelta(seconds=1)
    results = wait_for_state(bob,path,'results')['results']
    assert [entry['correct'] for entry in results] == [1,0]
    origin = datetime(2026, 1, 1)
    assert room_study.challenge_points(origin,iso(origin - timedelta(seconds=1)),30) == 1000
    assert room_study.challenge_points(origin,iso(origin + timedelta(milliseconds=50)),30) == 999
    assert room_study.challenge_points(origin,iso(origin + timedelta(seconds=60)),30) == 100


def test_chat_replay_transfer_and_close(anonymous_client, monkeypatch):
    from datetime import timedelta
    from app.models import utcnow
    from app.services import room_study

    async def generate(*args, **kwargs):
        return ['Distractor one','Distractor two','Distractor three']
    monkeypatch.setattr(room_study, 'get_or_generate_distractors', generate)

    make_users(anonymous_client, ('alice','bob','carol','david'), [
        ('alice','bob'),('alice','carol'),('bob','david'),
    ])
    alice, bob, carol, david = map(sign_in, ('alice','bob','carol','david'))
    path = make_room(alice)
    configure_room(alice,bob,path,deck(alice))
    view = wait_for_state(alice,path,'question')
    assert alice.post(path + '/invite',json={'username':'carol'}).status_code == 204
    assert join(carol,path).status_code == 204
    assert david.post(path + '/chat',json={'text':'Outsider'}).status_code == 404
    assert carol.post(path + '/chat',json={'text':'x' * 501}).status_code == 422
    for number in range(5):
        assert carol.post(path + '/chat',json={'text':f'Chat {number}'}).status_code == 204
    assert carol.post(path + '/chat',json={'text':'Too fast'}).status_code == 429
    assert [message['text'] for message in bob.get(path).json()['chat']] == [f'Chat {number}' for number in range(5)]

    option = view['question']['options'][0]['id']
    assert alice.post(path + '/answer',json=answer_for(view,option)).status_code == 204
    assert bob.post(path + '/answer',json=answer_for(view,option)).status_code == 204
    with anonymous_client.factory.begin() as db:
        db.get(RoomSession,view['session']['id']).deadline = utcnow() - timedelta(seconds=1)
    wait_for_state(alice,path,'results')
    assert bob.post(path + '/lobby').status_code == 403
    assert alice.post(path + '/lobby').status_code == 204
    lobby = bob.get(path).json()
    assert lobby['phase'] == 'lobby' and len(lobby['chat']) == 5
    assert not any(participant['spectator'] or participant['ready'] for participant in lobby['participants'])

    assert bob.post(path + '/leave',json={'action':'end'}).status_code == 403
    assert alice.post(path + '/leave',json={'action':'leave'}).status_code == 422
    assert alice.post(path + '/leave',json={'action':'transfer','username':'bob'}).status_code == 204
    assert alice.get(path).status_code == 404
    assert bob.get(path).json()['is_host']
    assert bob.get(path).json()['deck'] is None
    assert bob.post(path + '/invite',json={'username':'david'}).status_code == 204
    assert bob.post(path + '/leave',json={'action':'end'}).status_code == 204
    assert carol.get(path).status_code == 404
    assert david.get('/api/rooms').json()['invites'] == []
    with anonymous_client.factory() as db:
        result = db.get(RoomSession,view['session']['id'])
        assert result.completed_at is not None
        assert sum(row['answered'] for row in result.scores.values()) == 2


def test_disconnected_host_transfers_after_grace_and_room_expires(anonymous_client):
    from datetime import timedelta
    from app.models import RoomMember, StudyRoom, utcnow
    from app.services import room_study

    users = make_users(anonymous_client, ('alice','bob'), [('alice','bob')])
    alice, bob = map(sign_in, ('alice','bob'))
    path = make_room(alice)
    room_id = path.rsplit('/',1)[-1]
    assert join(bob,path).status_code == 204
    now = utcnow()
    with anonymous_client.factory.begin() as db:
        host = db.get(RoomMember,(room_id,users['alice']))
        host.seen_at = host.disconnected_at = now - timedelta(seconds=20)
    room_study.tick(anonymous_client.factory, None)
    assert alice.get(path).json()['is_host']
    assert not alice.get(path).json()['participants'][0]['connected']
    with anonymous_client.factory.begin() as db:
        host = db.get(RoomMember,(room_id,users['alice']))
        host.seen_at = host.disconnected_at = now - timedelta(seconds=46)
    room_study.tick(anonymous_client.factory, None)
    assert bob.get(path).json()['is_host']

    with anonymous_client.factory.begin() as db:
        db.get(StudyRoom,room_id).updated_at = now - timedelta(hours=1)
        for user_id in users.values():
            db.get(RoomMember,(room_id,user_id)).seen_at = now - timedelta(hours=1)
    room_study.tick(anonymous_client.factory, None)
    assert alice.get(path).status_code == 404
    assert bob.get('/api/rooms').json()['rooms'] == []


def test_preparation_skips_failed_questions_in_the_persisted_order(anonymous_client, monkeypatch):
    from app.services import room_study
    from app.services.distractor_cache import InsufficientDistractorsError

    attempted = []
    async def generate(card_id, *args, **kwargs):
        attempted.append(card_id)
        if len(attempted) == 1:
            raise InsufficientDistractorsError('Insufficient distractors.')
        return ['Distractor one','Distractor two','Distractor three']
    monkeypatch.setattr(room_study, 'get_or_generate_distractors', generate)
    make_users(anonymous_client, ('alice','bob'), [('alice','bob')])
    alice, bob = map(sign_in, ('alice','bob'))
    path = make_room(alice)
    configure_room(alice,bob,path,deck(alice,3))
    view = wait_for_state(alice,path,'question')
    assert view['session']['position'] == 1
    assert view['session']['failed'] == 1
    with anonymous_client.factory() as db:
        rows = list(db.scalars(select(RoomQuestion).order_by(RoomQuestion.position)))
        assert attempted == [row.card_id for row in rows]
        assert [row.failed for row in rows] == [True,False,False]


def test_room_migration_from_version_one_keeps_existing_deck(client):
    from sqlalchemy import text
    from app.database import SCHEMA_VERSION, init_database

    deck_id = deck(client,2)
    with client.factory.begin() as db:
        engine = db.get_bind()
        db.execute(text('BEGIN IMMEDIATE'))
        for table in ('study_room_messages','study_room_questions','study_room_sessions',
                      'study_room_invites','study_room_members','study_rooms'):
            db.execute(text(f'DROP TABLE {table}'))
        db.execute(text('PRAGMA user_version=1'))
    init_database(engine)
    with client.factory() as db:
        assert db.execute(text('PRAGMA user_version')).scalar_one() == SCHEMA_VERSION
        assert db.execute(text('SELECT COUNT(*) FROM study_rooms')).scalar_one() == 0
    assert client.get(f'/api/decks/{deck_id}').json()['card_count'] == 2
