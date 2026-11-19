import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

from app.database import get_db, get_write_db, init_database, make_engine
from app.main import app
from app.gwa.main import app as gwa_app
from app.auth.config import get_settings
from app.auth.service import create_user


@pytest.fixture(autouse=True)
def auth_configuration(monkeypatch):
    monkeypatch.setenv('AUTH_ENV', 'test')
    monkeypatch.setenv('AUTH_COOKIE_SECURE', 'false')
    monkeypatch.setenv('AUTH_TRUSTED_ORIGINS', 'http://testserver,http://localhost:8080,http://127.0.0.1:8080')
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def anonymous_client(tmp_path, monkeypatch):
    engine = make_engine(f"sqlite:///{(tmp_path / 'test.db').as_posix()}")
    init_database(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    def read_db():
        with factory() as db:
            yield db

    def write_db():
        with factory() as db:
            try:
                db.execute(text("BEGIN IMMEDIATE"))
                yield db
                db.commit()
            except Exception:
                db.rollback()
                raise

    app.dependency_overrides[get_db] = read_db
    app.dependency_overrides[get_write_db] = write_db
    gwa_app.dependency_overrides[get_db] = read_db
    gwa_app.dependency_overrides[get_write_db] = write_db
    monkeypatch.setattr("app.main.init_database", lambda: None)
    monkeypatch.setattr("app.services.multiple_choice.SessionLocal", factory)
    with TestClient(app) as test_client:
        test_client.factory = factory
        test_client.database_url = f"sqlite:///{(tmp_path / 'test.db').as_posix()}"
        yield test_client
    app.dependency_overrides.clear()
    gwa_app.dependency_overrides.clear()
    engine.dispose()


@pytest.fixture
def client(anonymous_client):
    with anonymous_client.factory() as db:
        user = create_user(db, 'owner@example.com', 'correct horse battery staple')
        anonymous_client.test_user_id = user.id
        db.commit()
    response = anonymous_client.post('/api/auth/login', json={
        'email':'owner@example.com', 'password':'correct horse battery staple'})
    assert response.status_code == 200, response.text
    anonymous_client.csrf_token = response.json()['csrf_token']
    anonymous_client.headers['X-CSRF-Token'] = anonymous_client.csrf_token
    return anonymous_client


def deck(client, count=1):
    response = client.post("/api/decks", json={"title": "Operating Systems"})
    assert response.status_code == 201, response.text
    created = response.json()
    for number in range(count):
        response = client.post(f"/api/decks/{created['id']}/cards", json={
            "front": f"Question {number}", "back": f"Answer {number}"})
        assert response.status_code == 201, response.text
    return created["id"]


def presentation(state):
    return {"presentation_number": state["presentation_number"], "presentation_token": state["presentation_token"]}


def review(client, state, difficulty="easy"):
    response = client.post(f"/api/study/{state['id']}/reveal", json=presentation(state))
    assert response.status_code == 200, response.text
    response = client.post(f"/api/study/{state['id']}/rate", json={**presentation(state), "difficulty": difficulty})
    assert response.status_code == 200, response.text
    return response.json()
