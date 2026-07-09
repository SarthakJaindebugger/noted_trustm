#!/usr/bin/env python3
"""print_admin_stats.py

Quick script to obtain a bearer token via the login route and fetch /api/v1/admin/stats.

Usage:
  python3 scripts/print_admin_stats.py --host http://127.0.0.1:8000 --username admin --password admin

If not provided, defaults to http://127.0.0.1:8000 and admin/admin.
"""
import argparse
import json
import sys
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError


def post_json(url: str, payload: dict, headers: dict | None = None) -> dict:
    body = json.dumps(payload).encode('utf-8')
    req = Request(url, data=body, headers={"Content-Type": "application/json", **(headers or {})}, method='POST')
    try:
        with urlopen(req, timeout=10) as resp:
            return json.load(resp)
    except HTTPError as e:
        try:
            msg = e.read().decode('utf-8')
        except Exception:
            msg = str(e)
        raise RuntimeError(f"HTTP error {e.code} on POST {url}: {msg}")
    except URLError as e:
        raise RuntimeError(f"Connection error on POST {url}: {e}")


def get_json(url: str, token: str | None = None) -> dict:
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = Request(url, headers=headers, method='GET')
    try:
        with urlopen(req, timeout=10) as resp:
            return json.load(resp)
    except HTTPError as e:
        try:
            msg = e.read().decode('utf-8')
        except Exception:
            msg = str(e)
        raise RuntimeError(f"HTTP error {e.code} on GET {url}: {msg}")
    except URLError as e:
        raise RuntimeError(f"Connection error on GET {url}: {e}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="http://127.0.0.1:8000", help="Backend base URL, e.g. http://127.0.0.1:8000")
    parser.add_argument("--username", default="admin", help="Login username")
    parser.add_argument("--password", default="admin", help="Login password")
    args = parser.parse_args()

    base = args.host.rstrip('/') + '/api/v1'
    login_url = base + '/auth/login'
    stats_url = base + '/admin/stats'

    try:
        print(f"Logging in as {args.username} -> {login_url}")
        resp = post_json(login_url, {"username": args.username, "password": args.password})
        token = resp.get('access_token')
        if not token:
            print('Login succeeded but no access_token returned', file=sys.stderr)
            print(json.dumps(resp, indent=2))
            sys.exit(1)
        print('Token obtained, fetching admin stats...')
        stats = get_json(stats_url, token=token)
        print(json.dumps(stats, indent=2, ensure_ascii=False))
    except Exception as e:
        print('Error:', e, file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
