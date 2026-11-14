"""Optional HTTP smoke test against an ISOLATED stack with a CLI-created test user.

python tests/manual_auth_http.py --base-url http://127.0.0.1:18081 --email verification@example.com
The password is prompted securely. Restart the isolated backend at the indicated pause.
"""
import argparse
import getpass
import http.cookiejar
import json
import time
from urllib.error import HTTPError
from urllib.request import HTTPCookieProcessor, Request, build_opener


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url', required=True)
    parser.add_argument('--email', required=True)
    args = parser.parse_args()
    password = getpass.getpass('Temporary test account password: ')
    jar = http.cookiejar.CookieJar()
    opener = build_opener(HTTPCookieProcessor(jar))
    origin = args.base_url.rstrip('/')

    def call(path, method='GET', data=None, csrf=None, origin_header=origin):
        headers = {'Origin':origin_header}
        if data is not None:
            headers['Content-Type'] = 'application/json'
        if csrf:
            headers['X-CSRF-Token'] = csrf
        request = Request(origin + path, method=method, headers=headers,
                          data=json.dumps(data).encode() if data is not None else None)
        try:
            response = opener.open(request, timeout=15)
        except HTTPError as error:
            response = error
        with response:
            raw = response.read()
            return response.status, json.loads(raw) if raw else None, response.headers

    assert call('/api/decks')[0] == 401
    assert call('/api/gwa/calculate', 'POST', {'courses':[{'units':3,'grade':1}]})[0] == 401
    status, user, headers = call('/api/auth/login', 'POST', {'email':args.email, 'password':password})
    del password
    assert status == 200, 'Login failed'
    csrf = user['csrf_token']
    cookie = next(iter(jar))
    assert 604000 < cookie.expires - time.time() <= 604800
    assert 'httponly' in headers['Set-Cookie'].lower()
    assert 'samesite=lax' in headers['Set-Cookie'].lower()
    assert call('/api/auth/me')[1]['id'] == user['id']
    assert call('/api/decks', 'POST', {'title':'Temporary HTTP smoke deck'})[0] == 403
    assert call('/api/decks', 'POST', {'title':'Temporary HTTP smoke deck'}, csrf, 'https://untrusted.invalid')[0] == 403
    status, deck, _ = call('/api/decks', 'POST', {'title':'Temporary HTTP smoke deck'}, csrf)
    assert status == 201
    try:
        assert call(f"/api/decks/{deck['id']}/cards", 'POST', {'front':'Q', 'back':'A'}, csrf)[0] == 201
        status, state, _ = call(f"/api/decks/{deck['id']}/study", 'POST', csrf=csrf)
        assert status == 201
        for _ in range(2):
            presentation = {key:state[key] for key in ('presentation_number','presentation_token')}
            assert call(f"/api/study/{state['id']}/reveal", 'POST', presentation, csrf)[0] == 200
            status, state, _ = call(f"/api/study/{state['id']}/rate", 'POST', {**presentation,'difficulty':'easy'}, csrf)
            assert status == 200
        assert state['status'] == 'completed'
        status, summary, _ = call('/api/gwa/calculate', 'POST', {'courses':[
            {'units':3,'grade':1.25}, {'units':2,'grade':2}]}, csrf)
        assert status == 200 and summary['gwa'] == 1.55
        assert summary['classification'] == 'Third Honor'
        assert call('/api/auth/me')[2]['Cache-Control'] == 'no-store'
        print('Login, seven-day cookie, CSRF, Flashcards, GWA and refresh checks passed.', flush=True)
        input('Restart the ISOLATED backend now, then press Enter: ')
        assert call('/api/auth/me')[1]['id'] == user['id'], 'Session lost on restart'
    finally:
        assert call(f"/api/decks/{deck['id']}", 'DELETE', csrf=csrf)[0] == 204
    old_cookie = f'{cookie.name}={cookie.value}'
    assert call('/api/auth/logout', 'POST', csrf=csrf)[0] == 204
    assert call('/api/auth/me')[0] == 401
    try:
        build_opener().open(Request(origin + '/api/auth/me', headers={'Cookie':old_cookie}), timeout=15)
        raise AssertionError('Revoked cookie was accepted')
    except HTTPError as error:
        assert error.code == 401
    print('Restart persistence, logout invalidation, replay rejection, and temporary deck cleanup passed.')


if __name__ == '__main__':
    main()
