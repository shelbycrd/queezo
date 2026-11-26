import os

import pytest
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
    assert alice.patch(path + '/settings',json={**settings,'share_private':False}).status_code == 204
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
    assert alice.patch(path + '/settings',json={'deck_id':deck(alice),'mode':'collaborative'}).status_code == 204
    for name in names[1:-2]:
        assert browsers[name].post(path + '/ready',json={'ready':True}).status_code == 204
    assert alice.get(path).json()['readiness'] == {'ready':4,'total':5}
    assert alice.post(path + '/start').status_code == 409
    assert browsers['frank'].post(path + '/ready',json={'ready':True}).status_code == 204
    assert alice.get(path).json()['readiness'] == {'ready':5,'total':5}
    assert alice.post(path + '/start').status_code == 204


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
    review = {'session_id':result['session']['id'], 'position':result['session']['position']}
    assert alice.post(path + '/pause',json={**review,'position':149,'paused':True}).status_code == 409
    assert alice.post(path + '/pause',json={**review,'paused':True}).status_code == 204
    assert wait_for_state(bob,path,'reveal')['session']['paused']
    assert bob.post(path + '/pause',json={**review,'paused':False}).status_code == 403
    assert alice.post(path + '/pause',json={**review,'paused':False}).status_code == 204


def test_challenge_timer_clamps_late_answers_and_ranks_by_points(anonymous_client, monkeypatch):
    from datetime import datetime, timedelta
    from threading import get_ident

    import pytest
    from fastapi import HTTPException

    from app.database import write_transaction
    from app.models import RoomMember, StudyRoom, utcnow
    from app.services import room_study
    from app.services.presenters import iso

    async def generate(*args, **kwargs):
        return ['Distractor one','Distractor two','Distractor three']
    monkeypatch.setattr(room_study, 'get_or_generate_distractors', generate)
    users = make_users(anonymous_client, ('alice','bob'), [('alice','bob')])
    alice, bob = map(sign_in, ('alice','bob'))
    path = make_room(alice)
    configure_room(alice,bob,path,deck(alice),mode='challenge')
    countdown = wait_for_state(alice,path,'countdown')
    guest_countdown = bob.get(path).json()
    assert guest_countdown['phase'] == 'countdown'
    assert guest_countdown['session']['deadline'] == countdown['session']['deadline']
    assert 'question' not in countdown and 'question' not in guest_countdown
    early_answer = {'session_id':countdown['session']['id'], 'position':0, 'option_id':'a3abf7f5-9207-4f47-aad3-a0e41f136cac'}
    assert alice.post(path + '/answer',json=early_answer).status_code == 409
    view = wait_for_state(alice,path,'question')
    with anonymous_client.factory() as db:
        session = db.get(RoomSession,view['session']['id'])
        question = db.get(RoomQuestion,(session.id,0))
        assert (session.deadline - session.opened_at).total_seconds() == 30
        correct_id = question.correct_id
    room_id = path.rsplit('/',1)[-1]
    test_thread = get_ident()
    with write_transaction(anonymous_client.factory) as db, monkeypatch.context() as clock:
        room = db.get(StudyRoom, room_id)
        session = db.get(RoomSession, view['session']['id'])
        bob_member = db.get(RoomMember, (room_id, users['bob']))
        alice_member = db.get(RoomMember, (room_id, users['alice']))
        deadline = session.deadline
        for elapsed in (timedelta(0), timedelta(microseconds=1)):
            current = deadline + elapsed
            clock.setattr(room_study, 'utcnow', lambda: current if get_ident() == test_thread else utcnow())
            with pytest.raises(HTTPException) as rejected:
                room_study.submit(db, room, bob_member, users['bob'], session.id, 0, correct_id)
            assert rejected.value.status_code == 409
        clock.setattr(room_study, 'utcnow', lambda: deadline - timedelta(microseconds=1) if get_ident() == test_thread else utcnow())
        room_study.submit(db, room, alice_member, users['alice'], session.id, 0, correct_id)
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

    make_users(anonymous_client, ('alice','carol','bob','david'), [
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
    assert alice.post(path + '/leave',json={'action':'leave'}).status_code == 204
    assert alice.get(path).status_code == 404
    assert bob.get(path).json()['is_host']
    assert bob.get(path).json()['deck'] is None
    assert bob.post(path + '/invite',json={'username':'david'}).status_code == 204
    assert not carol.get(path).json()['is_host']
    assert carol.post(path + '/leave',json={'action':'leave'}).status_code == 204
    assert bob.get(path).json()['is_host']
    assert bob.post(path + '/leave',json={'action':'leave'}).status_code == 204
    assert bob.get(path).status_code == 404
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


def test_first_reconnection_snapshot_marks_member_connected(anonymous_client):
    from datetime import timedelta

    from app.auth.config import get_settings
    from app.auth.service import hash_token
    from app.models import AuthSession, RoomMember, utcnow
    from app.routers.study_rooms import notification_state, socket_state

    users = make_users(anonymous_client, ('alice','bob'), [('alice','bob')])
    alice, bob = map(sign_in, ('alice','bob'))
    path = make_room(alice)
    assert join(bob,path).status_code == 204
    room_id = path.rsplit('/',1)[-1]
    with anonymous_client.factory.begin() as db:
        member = db.get(RoomMember, (room_id, users['bob']))
        member.seen_at = member.disconnected_at = utcnow() - timedelta(seconds=3)
    token = bob.cookies[get_settings().cookie_name]
    _, snapshot = socket_state(anonymous_client.factory, room_id, hash_token(token), refresh=True, reconnect=True)
    assert next(member for member in snapshot['participants'] if member['you'])['connected']

    token_hash = hash_token(token)
    with anonymous_client.factory.begin() as db:
        db.get(AuthSession, token_hash).expires_at = utcnow() - timedelta(seconds=1)
    assert socket_state(anonymous_client.factory, room_id, token_hash, refresh=True) is None
    assert notification_state(anonymous_client.factory, token_hash) is None


def test_concurrent_answers_score_once_and_session_finishes_when_only_spectators_remain(anonymous_client, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from datetime import timedelta

    from app.models import utcnow
    from app.services import room_study

    async def generate(*args, **kwargs):
        return ['Distractor one','Distractor two','Distractor three']

    monkeypatch.setattr(room_study, 'get_or_generate_distractors', generate)
    make_users(anonymous_client, ('alice','bob','carol'), [('alice','bob'),('alice','carol')])
    alice, bob, carol = map(sign_in, ('alice','bob','carol'))
    path = make_room(alice)
    deck_id = deck(alice, 2)
    assert alice.patch(f'/api/decks/{deck_id}', json={'visibility':'public'}).status_code == 200
    configure_room(alice,bob,path,deck_id)
    first = wait_for_state(alice,path,'question')
    assert alice.post(path + '/invite',json={'username':'carol'}).status_code == 204
    assert join(carol,path).status_code == 204
    answer = answer_for(first, first['question']['options'][0]['id'])
    with ThreadPoolExecutor(max_workers=2) as workers:
        replies = [workers.submit(browser.post, path + '/answer', json=answer) for browser in (alice,bob)]
        assert [reply.result().status_code for reply in replies] == [204,204]
    revealed = wait_for_state(carol,path,'reveal')
    assert len(revealed['question']['responses']) == 2
    with anonymous_client.factory.begin() as db:
        db.get(RoomSession,first['session']['id']).deadline = utcnow() - timedelta(seconds=1)
    second = wait_for_state(alice,path,'question')
    assert second['session']['position'] == 1
    for browser in (alice,bob):
        assert browser.post(path + '/leave',json={'action':'leave'}).status_code == 204
    room_study.tick(anonymous_client.factory, None)
    final = carol.get(path).json()
    assert final['phase'] == 'results'
    assert [result['answered'] for result in final['results']] == [1,1]
    assert [result['questions'] for result in final['results']] == [1,1]


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


def test_start_checks_only_connected_players_and_requires_the_host(anonymous_client, monkeypatch):
    from app.models import RoomMember, utcnow
    from app.services import room_study

    async def generate(*args, **kwargs):
        return ['Option one','Option two','Option three']
    monkeypatch.setattr(room_study, 'get_or_generate_distractors', generate)

    users = make_users(anonymous_client, ('alice','bob','carol','david','elsie'),
                       [('alice',name) for name in ('bob','carol','david','elsie')])
    alice, bob, carol, david = map(sign_in, ('alice','bob','carol','david'))
    path = make_room(alice)
    room_id = path.rsplit('/',1)[1]
    deck_id = deck(alice)
    assert alice.post(path + '/invite',json={'username':'elsie'}).status_code == 204
    for browser, name in ((carol,'carol'),(david,'david')):
        assert alice.post(path + '/invite',json={'username':name}).status_code == 204
        assert join(browser,path).status_code == 204
    assert join(bob,path).status_code == 204
    assert alice.patch(path + '/settings',json={'deck_id':deck_id,'mode':'collaborative','share_private':True}).status_code == 204

    with anonymous_client.factory.begin() as db:
        db.get(RoomMember,(room_id,users['carol'])).spectator = True
    assert bob.post(path + '/ready',json={'ready':True}).status_code == 204
    assert alice.get(path).json()['readiness_blocker']
    assert alice.post(path + '/start').status_code == 409

    with anonymous_client.factory.begin() as db:
        db.get(RoomMember,(room_id,users['david'])).disconnected_at = utcnow()
        db.get(RoomMember,(room_id,users['alice'])).disconnected_at = utcnow()
    assert alice.post(path + '/start').status_code == 409
    with anonymous_client.factory.begin() as db:
        db.get(RoomMember,(room_id,users['alice'])).disconnected_at = None
    assert alice.get(path).json()['readiness_blocker'] is None
    assert alice.post(path + '/start').status_code == 204
    with anonymous_client.factory() as db:
        session = db.scalar(select(RoomSession).where(RoomSession.room_id == room_id))
        assert {player['username'] for player in session.players.values()} == {'alice','bob'}


def test_initial_invite_pushes_and_resynchronizes_without_duplicates(anonymous_client):
    from app.auth.config import get_settings
    from app.models import StudyRoom

    make_users(anonymous_client, ('alice','bob','carol'), [('alice','bob')])
    alice, bob, carol = map(sign_in, ('alice','bob','carol'))
    cookie = get_settings().cookie_name
    headers = {'origin':'http://testserver','cookie':cookie + '=' + bob.cookies[cookie]}
    endpoint = '/api/rooms/notifications/live'
    with anonymous_client.websocket_connect(endpoint,headers=headers) as live:
        assert live.receive_json()['invites'] == []
        assert alice.post('/api/rooms',json={'username':'carol'}).status_code == 404
        with anonymous_client.factory() as db:
            assert not list(db.scalars(select(StudyRoom)))
        path = make_room(alice)
        room_id = path.rsplit('/',1)[1]
        snapshot = live.receive_json()
        assert [item['room_id'] for item in snapshot['invites']] == [room_id]
        assert snapshot['invites'][0]['sender']['username'] == 'alice'
        assert carol.get('/api/rooms').json()['invites'] == []
        assert alice.post(path + '/invite',json={'username':'bob'}).status_code == 204
    with anonymous_client.websocket_connect(endpoint,headers=headers) as rejoined:
        assert [item['room_id'] for item in rejoined.receive_json()['invites']] == [room_id]
        assert join(bob,path).status_code == 204
        update = rejoined.receive_json()
        assert update['invites'] == []
        assert [item['id'] for item in update['rooms']] == [room_id]
        second_room = make_room(alice)
        assert rejoined.receive_json()['invites'][0]['room_id'] == second_room.rsplit('/',1)[1]
        assert bob.post(second_room + '/invitation',json={'accept':False}).status_code == 204
        assert rejoined.receive_json()['invites'] == []
        assert bob.get(second_room).status_code == 404


def test_room_friends_paginate_and_show_members_and_pending_invites(anonymous_client):
    names = ('alice','bob','carol','david','elsie','frank','grace')
    make_users(anonymous_client, names, [('alice',name) for name in names[1:]])
    alice, bob, frank = map(sign_in, ('alice','bob','frank'))
    path = make_room(alice)
    endpoint = path + '/friends'
    assert frank.get(endpoint).status_code == 404
    first = alice.get(endpoint).json()
    assert first['has_next']
    assert [(row['username'],row['status']) for row in first['items']] == [
        ('bob','invited'),('carol','available'),('david','available'),('elsie','available')]
    second = alice.get(endpoint + '?page=2').json()
    assert not second['has_next'] and [row['username'] for row in second['items']] == ['frank','grace']
    assert alice.post(path + '/invite',json={'username':'frank'}).status_code == 204
    assert alice.get(endpoint + '?page=2').json()['items'][0]['status'] == 'invited'
    assert join(bob,path).status_code == 204
    assert alice.get(endpoint).json()['items'][0]['status'] == 'member'
    assert bob.get(endpoint).json()['items'][0]['username'] == 'alice'
    assert bob.get(path + '/decks').status_code == 403


def test_owned_decks_of_all_visibilities_are_selectable_without_granting_deck_access(anonymous_client):
    from app.models import Deck, Flashcard

    make_users(anonymous_client, ('alice','bob','carol'), [('alice','bob')])
    alice, bob, carol = map(sign_in, ('alice','bob','carol'))
    path = make_room(alice)
    assert join(bob,path).status_code == 204
    assert alice.post(path + '/ready',json={'ready':True}).status_code == 403
    for visibility in ('public','unlisted','private'):
        deck_id = deck(alice,2)
        assert alice.patch(f'/api/decks/{deck_id}',json={'visibility':visibility}).status_code == 200
        assert bob.post(path + '/ready',json={'ready':True}).status_code == 204
        assert alice.patch(path + '/settings',json={'deck_id':deck_id,'mode':'collaborative'}).status_code == 204
        snapshot = bob.get(path).json()
        assert snapshot['deck']['id'] == deck_id
        assert snapshot['readiness'] == {'ready':0,'total':1}
        assert carol.get(path).status_code == 404
        assert bob.get(f'/api/decks/{deck_id}').status_code == 404
        assert bob.patch(f'/api/decks/{deck_id}',json={'title':'Attempt'}).status_code == 404
        if visibility == 'private':
            with anonymous_client.factory() as db:
                token = db.get(Deck,deck_id).share_token
                card_id = db.scalar(select(Flashcard.id).where(Flashcard.deck_id == deck_id))
            assert bob.get(f'/api/shared/decks/{token}').status_code == 404
            assert bob.post(f'/api/shared/decks/{token}/copy').status_code == 404
            assert bob.patch(f'/api/cards/{card_id}',json={'front':'Attempt'}).status_code == 404


def test_room_opens_progressively_and_waits_without_a_challenge_deadline(anonymous_client, monkeypatch):
    import asyncio
    from datetime import timedelta
    from threading import Event

    from app.models import utcnow
    from app.services import room_study

    release = Event()
    generated = []

    async def generate(card_id, *args, **kwargs):
        generated.append(card_id)
        if len(generated) == 6:
            while not release.is_set():
                await asyncio.sleep(.02)
        return ['Distractor one','Distractor two','Distractor three']

    monkeypatch.setattr(room_study, 'get_or_generate_distractors', generate)
    make_users(anonymous_client, ('alice','bob'), [('alice','bob')])
    alice, bob = map(sign_in, ('alice','bob'))
    path = make_room(alice)
    configure_room(alice,bob,path,deck(alice,6),mode='challenge')
    try:
        view = wait_for_state(alice,path,'question')
        assert view['session']['position'] == 0
        assert view['session']['deadline']
        with anonymous_client.factory() as db:
            rows = list(db.scalars(select(RoomQuestion).order_by(RoomQuestion.position)))
            assert len([row for row in rows if row.options]) == 5
            assert generated[:5] == [row.card_id for row in rows[:5]]
        for position in range(5):
            view = wait_for_state(alice,path,'question')
            assert view['session']['position'] == position
            option = view['question']['options'][0]['id']
            assert alice.post(path + '/answer',json=answer_for(view,option)).status_code == 204
            assert bob.post(path + '/answer',json=answer_for(view,option)).status_code == 204
            with anonymous_client.factory.begin() as db:
                db.get(RoomSession,view['session']['id']).deadline = utcnow() - timedelta(seconds=1)
        stalled = wait_for_state(bob,path,'waiting')
        assert stalled['session']['position'] == 5
        assert stalled['session']['deadline'] is None
        assert 'question' not in stalled
        release.set()
        next_view = wait_for_state(bob,path,'question')
        assert next_view['session']['position'] == 5
        assert next_view['session']['deadline']
        assert len(generated) == len(set(generated)) == 6
    finally:
        release.set()


def test_room_settings_reject_a_stale_revision(anonymous_client):
    make_users(anonymous_client, ('alice','bob'), [('alice','bob')])
    alice = sign_in('alice')
    path = make_room(alice)
    revision = alice.get(path).json()['settings_revision']
    settings = {'mode':'challenge','seconds':45,'expected_revision':revision}
    assert alice.patch(path + '/settings',json=settings).status_code == 204
    assert alice.patch(path + '/settings',json={**settings,'seconds':70}).status_code == 409
    assert alice.get(path).json()['seconds'] == 45


@pytest.mark.parametrize("variant", [
    "solo-ollama", "room-fallback",
    pytest.param("live-ollama", marks=pytest.mark.skipif(
        os.getenv("QUEEZO_TEST_LIVE_SHARED") != "1", reason="requires local Ollama",
    )),
])
def test_distractors_shared_across_solo_readers_and_rooms(anonymous_client, monkeypatch, variant):
    from time import monotonic, sleep
    from unittest.mock import AsyncMock

    import httpx

    from app.models import Deck, FlashcardDistractorCache
    from app.services import distractor_cache, distractors
    from app.services.distractors import DistractorGenerationError
    from test_multiple_choice import wait_for_state as wait_for_solo

    monkeypatch.setattr(distractor_cache, "SessionLocal", anonymous_client.factory)
    make_users(anonymous_client, ('alice','bob'), [('alice','bob')])
    alice, bob = map(sign_in, ('alice','bob'))
    # Keep both clients on the lifespan’s event loop so solo jobs outlive the POST.
    alice.portal = bob.portal = anonymous_client.portal
    live = variant == 'live-ollama'
    room_first = variant == 'room-fallback'
    deck_id = deck(alice, 0 if live else 4)
    if live:
        for country, capital in [('France','Paris'),('Japan','Tokyo'),('Italy','Rome'),('Egypt','Cairo')]:
            assert alice.post(f'/api/decks/{deck_id}/cards', json={
                'front':f'What is the capital of {country}?', 'back':capital,
            }).status_code == 201
    assert alice.patch(f'/api/decks/{deck_id}', json={'visibility':'public'}).status_code == 200
    with anonymous_client.factory() as db:
        token = db.get(Deck, deck_id).share_token
        assert db.scalars(select(FlashcardDistractorCache)).all() == []

    requests = []
    if live:
        original = httpx.AsyncClient.post

        async def counted_post(client, url, **kwargs):
            if str(url).endswith('/api/chat'):
                requests.append(url)
            return await original(client, url, **kwargs)

        monkeypatch.setattr(httpx.AsyncClient, "post", counted_post)
        generate = AsyncMock(wraps=distractors.generate_distractors)
    elif room_first:
        generate = AsyncMock(side_effect=DistractorGenerationError("Offline", reason="ollama_unavailable"))
    else:
        generate = AsyncMock(return_value=['First distractor','Second distractor','Third distractor'])
    monkeypatch.setattr(distractors, "generate_distractors", generate)

    def prepare_solo(browser, shared=False):
        before = monotonic()
        endpoint = f'/api/shared/decks/{token}/multiple-choice' if shared else f'/api/decks/{deck_id}/multiple-choice'
        start = browser.post(endpoint)
        assert start.status_code == 202, start.text
        state = start.json()
        path = f"/api/multiple-choice/{state['id']}"
        if live:
            deadline = monotonic() + 180
            while monotonic() < deadline:
                ready = browser.get(path).json()
                if ready['status'] in ('active', 'failed'):
                    break
                sleep(.15)
            assert ready['status'] == 'active', ready['failures']
        else:
            ready = wait_for_solo(browser, path, "active")
        assert ready['progress']['ready'] == 4
        return path, ready, monotonic() - before

    def prepare_room():
        # A non-owner hosts the same public deck. The other member sees the same snapshot.
        path = make_room(bob, 'alice')
        before = monotonic()
        configure_room(bob,alice,path,deck_id)
        wait_for_state(bob,path,'countdown')
        return path, monotonic() - before

    if room_first:
        room_path, cold_time = prepare_room()
        _, _, warm_time = prepare_solo(alice)
    else:
        _, _, cold_time = prepare_solo(alice)
        room_path, warm_time = prepare_room()
    assert generate.await_count == 4
    initial_requests = len(requests)
    if live:
        assert initial_requests >= 4
    generate.reset_mock()
    generate.side_effect = AssertionError("Warm preparation must not call Ollama")
    reader_path, reader, reader_time = prepare_solo(bob, shared=True)
    assert reader['shared'] and reader['deck_id'] is None
    question = bob.post(reader_path + '/question').json()['question']
    assert len(question['options']) == 4 and 'correct_option_id' not in question
    assert alice.get(reader_path).status_code == 404
    prepare_solo(alice, shared=True)
    history = alice.get(f'/api/decks/{deck_id}/multiple-choice/sessions').json()
    assert len(history) == 1 and not history[0].get('shared')
    host_question = wait_for_state(bob,room_path,'question')['question']
    guest_question = wait_for_state(alice,room_path,'question')['question']
    assert host_question['options'] == guest_question['options']
    assert 'correct_id' not in guest_question
    if not live:
        assert {option['text'] for option in host_question['options']} >= (
            {'Answer 0','Answer 1','Answer 2','Answer 3'} if room_first else
            {'First distractor','Second distractor','Third distractor'}
        )
    generate.assert_not_awaited()
    assert len(requests) == initial_requests

    with anonymous_client.factory() as db:
        cached = db.scalars(select(FlashcardDistractorCache)).all()
        assert len(cached) == 4
        fallback_entries = sum(entry.source == 'fallback' for entry in cached)
        if not live:
            assert fallback_entries == (4 if room_first else 0)
    # Sharing changes revoke access without deleting valid cache rows.
    assert alice.patch(f'/api/decks/{deck_id}', json={'visibility':'private'}).status_code == 200
    assert bob.get(reader_path).status_code == 404
    assert bob.post(f'/api/shared/decks/{token}/multiple-choice').status_code == 404
    assert bob.post(f'/api/decks/{deck_id}/multiple-choice').status_code == 404
    with anonymous_client.factory() as db:
        assert len(db.scalars(select(FlashcardDistractorCache)).all()) == 4
    print(f"shared-cache benchmark: {variant} cold={cold_time:.3f}s "
          f"warm_other_mode={warm_time:.3f}s warm_reader={reader_time:.3f}s "
          f"cold_generator_calls=4 cold_http_requests={initial_requests} warm_http_requests=0 "
          f"fallback_entries={fallback_entries}")


def test_invites_are_limited_per_pair_in_a_rolling_window_without_revealing_the_limit(anonymous_client):
    from datetime import timedelta
    from app.models import LoginThrottle, utcnow
    from app.services import study_rooms

    make_users(anonymous_client, ('alice','bob','carol'), [('alice','bob'), ('alice','carol')])
    alice, bob = sign_in('alice'), sign_in('bob')
    path = make_room(alice)
    for _ in range(study_rooms.INVITE_PAIR_LIMIT - 1):
        assert alice.post(path + '/invite',json={'username':'bob'}).status_code == 204
    for attempt in (lambda: alice.post(path + '/invite',json={'username':'bob'}),
                    lambda: alice.post('/api/rooms',json={'username':'bob'})):
        refused = attempt()
        assert refused.status_code == 429
        body = refused.text
        assert refused.json()['error']['message'] == "You've sent too many invitations to this user. Please try again later."
        assert 'retry-after' not in {key.lower() for key in refused.headers}
        assert not any(str(value) in body for value in ('5', '60', 'remaining', 'seconds'))
    assert len(bob.get('/api/rooms').json()['invites']) == 1
    assert alice.post(path + '/invite',json={'username':'carol'}).status_code == 204
    # Rolling window: once the oldest attempt ages out, exactly one more slot opens.
    with anonymous_client.factory.begin() as db:
        oldest = min(db.scalars(select(LoginThrottle).where(LoginThrottle.key.like('room-invite-pair:%'))),
                     key=lambda row: row.window_started)
        oldest.window_started = utcnow() - timedelta(seconds=61)
    assert alice.post(path + '/invite',json={'username':'bob'}).status_code == 204
    assert alice.post(path + '/invite',json={'username':'bob'}).status_code == 429


def test_concurrent_invites_cannot_bypass_the_pair_limit_or_duplicate(anonymous_client):
    from concurrent.futures import ThreadPoolExecutor
    from app.models import RoomInvite, StudyRoom
    from app.services import study_rooms

    make_users(anonymous_client, ('alice','bob'), [('alice','bob')])
    alice = sign_in('alice')
    with ThreadPoolExecutor(8) as pool:
        codes = list(pool.map(lambda _: alice.post('/api/rooms',json={'username':'bob'}).status_code, range(12)))
    assert codes.count(201) == study_rooms.INVITE_PAIR_LIMIT
    assert set(codes) == {201, 429}
    with anonymous_client.factory() as db:
        assert len(list(db.scalars(select(StudyRoom)))) == 1
        assert len(list(db.scalars(select(RoomInvite)))) == 1


def test_repeated_invites_keep_one_active_invitation_per_pair(anonymous_client):
    make_users(anonymous_client, ('alice','bob','carol'), [('alice','bob'), ('alice','carol')])
    alice, bob, carol = map(sign_in, ('alice','bob','carol'))
    first = make_room(alice)
    assert make_room(alice) == first
    second = make_room(alice, 'carol')
    assert alice.post(second + '/invite',json={'username':'bob'}).status_code == 204
    invites = bob.get('/api/rooms').json()['invites']
    assert [item['room_id'] for item in invites] == [second.rsplit('/',1)[1]]
    assert join(bob, first).status_code == 404
    assert join(bob, second).status_code == 204
    assert len(carol.get('/api/rooms').json()['invites']) == 1
