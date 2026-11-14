import pytest
from fastapi.testclient import TestClient

from app.gwa.main import app


@pytest.fixture
def gwa_client(client):
    with TestClient(app) as gwa:
        gwa.cookies.update(client.cookies)
        gwa.headers.update(client.headers)
        yield gwa


def calculate(client, courses):
    response = client.post('/api/gwa/calculate', json={'courses': courses})
    assert response.status_code == 200, response.text
    return response.json()


def test_weighted_average_and_course_summary(gwa_client):
    result = calculate(gwa_client, [
        {'subject': '  Mathematics  ', 'units': 3, 'grade': 1},
        {'subject': '', 'units': 1, 'grade': 3},
    ])
    assert result == {
        'courses': [
            {'subject': 'Mathematics', 'units': 3, 'grade': 1, 'weighted_grade': 3},
            {'subject': None, 'units': 1, 'grade': 3, 'weighted_grade': 3},
        ],
        'course_count': 2, 'total_units': 4, 'total_weighted_grades': 6,
        'gwa': 1.5, 'gwa_display': '1.50', 'percentage': 87.5,
        'classification': 'Second Honor', 'honor': 'Second Honor',
        'performance': 'Passing',
        'honor_eligible': True, 'is_passing': True, 'failed_course_count': 0,
    }


@pytest.mark.parametrize('grade,label,percentage', [
    (1, 'First Honor', 100), (1.25, 'First Honor', 93.75),
    (1.250001, 'Second Honor', 93.75), (1.5, 'Second Honor', 87.5),
    (1.500001, 'Third Honor', 87.5), (1.75, 'Third Honor', 81.25),
    (1.750001, 'Passing', 81.25), (3, 'Passing', 50),
    (3.000001, 'Failed', 50), (5, 'Failed', 0),
])
def test_exact_classification_boundaries_before_display_rounding(gwa_client, grade, label, percentage):
    result = calculate(gwa_client, [{'units': 3, 'grade': grade}])
    assert result['classification'] == label
    assert result['honor'] == (label if 'Honor' in label else None)
    assert result['is_passing'] == (grade <= 3)
    assert result['honor_eligible'] == (grade <= 1.75)
    assert result['percentage'] == percentage
    assert result['failed_course_count'] == int(grade > 3)
    expected_performance = 'Excellent' if grade == 1 else 'Just passing' if grade == 3 else 'Passing' if grade <= 3 else 'Failed'
    assert result['performance'] == expected_performance


def test_one_and_fifteen_courses_and_optional_subject(gwa_client):
    for count in [1, 15]:
        result = calculate(gwa_client, [{'units': 3, 'grade': 1.75}] * count)
        assert result['course_count'] == count
        assert result['total_units'] == 3 * count
        assert result['gwa'] == 1.75
        assert all(course['subject'] is None for course in result['courses'])


def test_decimal_units_and_half_up_display_rounding(gwa_client):
    result = calculate(gwa_client, [
        {'units': '0.1', 'grade': '1.25'}, {'units': '0.2', 'grade': '1.25'},
    ])
    assert result['total_units'] == 0.3
    assert result['classification'] == 'First Honor'
    rounded = calculate(gwa_client, [{'subject': None, 'units': 0.5, 'grade': 1.755}])
    assert rounded['gwa_display'] == '1.76'
    assert rounded['gwa'] == 1.76
    assert rounded['classification'] == 'Passing'


def test_failed_subject_is_reported_separately_from_average(gwa_client):
    result = calculate(gwa_client, [{'units': 12, 'grade': 1}, {'units': 1, 'grade': 5}])
    assert result['classification'] == 'Second Honor'
    assert result['failed_course_count'] == 1


@pytest.mark.parametrize('payload', [
    {}, {'courses': []}, {'courses': [{'units': 3, 'grade': 1}] * 16},
    {'courses': None}, {'courses': [None]}, {'courses': [{}]},
    {'courses': [{'units': 3}]}, {'courses': [{'grade': 1}]},
    {'courses': [{'units': 3, 'grade': 1}], 'unknown': True},
])
def test_invalid_course_lists(gwa_client, payload):
    response = gwa_client.post('/api/gwa/calculate', json=payload)
    assert response.status_code == 422
    assert response.json()['error']['details']


@pytest.mark.parametrize('field,value', [
    ('units', 0), ('units', -1), ('units', None), ('units', True),
    ('units', ''), ('units', 'abc'), ('units', 'NaN'), ('units', 'Infinity'),
    ('units', 100000000), ('units', '0.00001'),
    ('grade', 0.99), ('grade', 5.01), ('grade', None), ('grade', False),
    ('grade', ''), ('grade', 'abc'), ('grade', 'NaN'), ('grade', '-Infinity'),
    ('grade', '1.0000001'), ('subject', 42), ('subject', 'a' * 121),
    ('unknown', 1),
])
def test_invalid_course_fields(gwa_client, field, value):
    course = {'units': 3, 'grade': 1.25, field: value}
    response = gwa_client.post('/api/gwa/calculate', json={'courses': [course]})
    assert response.status_code == 422
    assert response.json()['error']['details']


def test_apps_have_separate_routes_and_openapi(gwa_client, client):
    assert gwa_client.get('/api/gwa/health').json() == {'status': 'ok'}
    assert gwa_client.get('/gwa/docs').status_code == 200
    schema = gwa_client.get('/gwa/openapi.json').json()
    assert '/api/gwa/calculate' in schema['paths']
    assert '/api/decks' not in schema['paths']
    assert gwa_client.get('/api/decks').status_code == 404
    assert client.post('/api/gwa/calculate', json={}).status_code == 404
    assert '/api/gwa/calculate' not in client.get('/openapi.json').json()['paths']
