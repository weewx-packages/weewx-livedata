#
#    Copyright (c) 2026 Manuel Hilgert
#
#    See the file LICENSE.txt for your rights.
#
"""The two halves against each other: Python signs, live.php checks.

This is the test that matters most, because live.php is the half that ends up on
somebody else's web space. Nothing in the repository can fix a copy that is
already out there, so the agreement between the two has to hold from the start.

It runs against PHP's built-in server rather than the command line. In CLI,
`php://input` is not connected to standard input, so a command line harness
proves nothing about the path a real request takes.

Skipped where there is no php. Run with:

    PYTHONPATH=bin:/path/to/weewx/src pytest tests/
"""

import hashlib
import hmac
import io
import json
import os
import shutil
import socket
import subprocess
import time
import urllib.error
import urllib.request

import pytest

SECRET = 'abcdef0123456789'
HERE = os.path.dirname(os.path.abspath(__file__))
LIVE_PHP = os.path.join(os.path.dirname(HERE), 'live.php')

pytestmark = pytest.mark.skipif(shutil.which('php') is None, reason="needs php")


def free_port():
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


@pytest.fixture
def endpoint(tmp_path):
    """live.php with a known secret, served over HTTP.

    Yields:
        tuple[str, str]: The URL to post to, and the path the file lands at.
    """
    text = io.open(LIVE_PHP, encoding='utf-8').read()
    assert "$SECRET   = 'replace_me';" in text, "the installer's anchor has moved"
    target = tmp_path / 'live.php'
    target.write_text(text.replace("$SECRET   = 'replace_me';",
                                   "$SECRET   = '%s';" % SECRET, 1),
                      encoding='utf-8')

    port = free_port()
    server = subprocess.Popen(['php', '-S', '127.0.0.1:%d' % port, '-t', str(tmp_path)],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    url = 'http://127.0.0.1:%d/live.php' % port
    try:
        for _ in range(100):
            try:
                urllib.request.urlopen(url, timeout=1)
            except urllib.error.HTTPError:
                break                       # answering, which is all we need
            except OSError:
                time.sleep(0.05)
        else:
            pytest.fail("php server did not come up")
        yield url, str(tmp_path / 'live.json')
    finally:
        server.terminate()
        server.wait(timeout=10)


def post(url, body, stamp=None, sig=None, content_type='application/json'):
    """One request, signed the way the service signs it.

    Returns:
        tuple[int, str]: The status code and the body of the reply.
    """
    stamp = stamp or str(int(time.time()))
    if sig is None:
        sig = hmac.new(SECRET.encode(), stamp.encode() + body, hashlib.sha256).hexdigest()
    request = urllib.request.Request(url, data=body)
    request.add_header('Content-Type', content_type)
    request.add_header('X-Timestamp', stamp)
    request.add_header('X-Signature', sig)
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status, response.read().decode().strip()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode().strip()


PAYLOAD = json.dumps({'dateTime': 1788000000, 'usUnits': 1,
                      'current': {'outTemp': 20.5}, 'day': {}},
                     separators=(',', ':')).encode('utf-8')


def test_a_signed_post_is_written_byte_for_byte(endpoint):
    url, written = endpoint

    status, _ = post(url, PAYLOAD)

    assert status == 204
    assert io.open(written, 'rb').read() == PAYLOAD


def test_python_and_php_compute_the_same_signature(endpoint):
    """The one agreement that cannot be changed later without a re-upload."""
    url, _ = endpoint
    from user.livedata import LiveDataThread
    import queue

    thread = LiveDataThread(queue.Queue(), server_url=url, secret=SECRET)
    stamp = str(int(time.time()))

    status, _ = post(url, PAYLOAD, stamp=stamp, sig=thread.signature(stamp, PAYLOAD))

    assert status == 204


def test_a_wrong_signature_is_refused(endpoint):
    url, written = endpoint

    status, why = post(url, PAYLOAD, sig='0' * 64)

    assert status == 401 and 'signature' in why.lower()
    assert not os.path.exists(written), "refused, but it wrote anyway"


def test_a_captured_post_goes_stale(endpoint):
    """The timestamp is signed, so an old one cannot be re-sent with its signature."""
    url, written = endpoint
    old = str(int(time.time()) - 300)

    status, _ = post(url, PAYLOAD, stamp=old)

    assert status == 401
    assert not os.path.exists(written)


def test_a_body_that_is_not_json_is_refused(endpoint):
    url, written = endpoint

    status, _ = post(url, b'not json at all')

    assert status == 400
    assert not os.path.exists(written)


def test_a_get_is_refused(endpoint):
    url, _ = endpoint

    try:
        with urllib.request.urlopen(url, timeout=10) as response:
            status = response.status
    except urllib.error.HTTPError as e:
        status = e.code

    assert status == 405
