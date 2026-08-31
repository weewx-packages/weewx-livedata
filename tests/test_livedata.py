#
#    Copyright (c) 2026 Manuel Hilgert
#
#    See the file LICENSE.txt for your rights.
#
"""What the service puts on the queue, and what the thread does with it.

Run with:

    PYTHONPATH=bin:/path/to/weewx/src pytest tests/
"""

import hashlib
import hmac
import json
import queue

import pytest

import weewx
import weewx.restx
from user.livedata import LiveDataThread, StdLiveData, _as_list

SECRET = 'abcdef0123456789'
NOW = 1788000000


def packet(timestamp, **values):
    p = {'dateTime': int(timestamp), 'usUnits': weewx.US}
    p.update(values)
    return p


class Engine:
    """Just enough engine to let a service bind and be built."""

    def __init__(self):
        self.callbacks = {}

    def bind(self, event_type, callback):
        self.callbacks.setdefault(event_type, []).append(callback)


def build(**overrides):
    """A service with its thread and its database access taken out.

    The thread would post over the network and the database is not what these
    tests are about. What is left is the part that decides what gets posted.
    """
    site = {'url': 'https://example.com/live.php', 'secret': SECRET}
    site.update(overrides)

    service = StdLiveData.__new__(StdLiveData)
    service.engine = Engine()
    service.extremes = _as_list(site.get('extremes'))
    service.cache = weewx.restx.CachedValues()
    service.day = {}
    service.queue = queue.Queue()
    return service


class TestThePayload:

    def test_a_reading_from_an_earlier_packet_is_still_in_it(self):
        """A Vantage sends temperature in one packet and wind in the next."""
        service = build()
        service.cache.update(packet(NOW, outTemp=20.0), NOW)
        service.cache.update(packet(NOW + 2, windSpeed=5.0), NOW + 2)

        current = service._payload(NOW + 2)['current']

        assert current['outTemp'] == 20.0
        assert current['windSpeed'] == 5.0

    def test_it_carries_the_unit_system_rather_than_formatted_text(self):
        """The page converts, from the table the JSON generator writes."""
        service = build()
        service.cache.update(packet(NOW, outTemp=68.0), NOW)

        payload = service._payload(NOW)

        assert payload['usUnits'] == weewx.US
        assert payload['current']['outTemp'] == 68.0

    def test_a_reading_that_never_arrived_is_left_out(self):
        service = build()
        service.cache.update(packet(NOW, outTemp=20.0), NOW)

        assert 'windSpeed' not in service._payload(NOW)['current']

    def test_the_timestamp_is_the_packet_that_prompted_it(self):
        service = build()
        service.cache.update(packet(NOW, outTemp=20.0), NOW)

        assert service._payload(NOW)['dateTime'] == NOW


class TestTheDailyExtremes:
    """Rich Bell on #1133: a live reading beside a stale high looks wrong."""

    def test_a_new_high_moves_with_the_packet(self):
        service = build()
        service.day = {'outTemp': {'min': 10.0, 'max': 20.0}}

        service._raise_extremes(packet(NOW, outTemp=25.0))

        assert service.day['outTemp']['max'] == 25.0
        assert service.day['outTemp']['min'] == 10.0

    def test_a_new_low_moves_with_the_packet(self):
        service = build()
        service.day = {'outTemp': {'min': 10.0, 'max': 20.0}}

        service._raise_extremes(packet(NOW, outTemp=5.0))

        assert service.day['outTemp']['min'] == 5.0

    def test_a_reading_in_between_moves_neither(self):
        service = build()
        service.day = {'outTemp': {'min': 10.0, 'max': 20.0}}

        service._raise_extremes(packet(NOW, outTemp=15.0))

        assert service.day['outTemp'] == {'min': 10.0, 'max': 20.0}

    def test_a_day_with_no_readings_yet_takes_the_first_one(self):
        """The database has nothing at midnight, so both ends start at None."""
        service = build()
        service.day = {'outTemp': {'min': None, 'max': None}}

        service._raise_extremes(packet(NOW, outTemp=15.0))

        assert service.day['outTemp'] == {'min': 15.0, 'max': 15.0}

    def test_an_observation_missing_from_a_packet_is_left_alone(self):
        service = build()
        service.day = {'outTemp': {'min': 10.0, 'max': 20.0}}

        service._raise_extremes(packet(NOW, windSpeed=5.0))

        assert service.day['outTemp'] == {'min': 10.0, 'max': 20.0}


class TestReadingTheOptions:
    """ConfigObj hands the same option back in two shapes."""

    def test_a_bare_line_arrives_as_a_list(self):
        assert _as_list(['outTemp', 'windSpeed']) == ['outTemp', 'windSpeed']

    def test_a_quoted_line_arrives_as_one_string(self):
        """This is what a written configuration looks like, and it cost an hour.

        ConfigObj quotes a value holding commas when it writes it, and hands the
        whole thing back as one name. The query built from that fails with a SQL
        syntax error that says nothing about where it came from.
        """
        assert _as_list('outTemp, windSpeed') == ['outTemp', 'windSpeed']

    def test_nothing_means_nothing(self):
        assert _as_list(None) == []
        assert _as_list('') == []
        assert _as_list([]) == []

    def test_stray_commas_and_spaces_are_dropped(self):
        assert _as_list('outTemp,, windSpeed , ') == ['outTemp', 'windSpeed']


class TestTheSignature:

    @staticmethod
    def thread(**overrides):
        options = {'server_url': 'https://example.com/live.php', 'secret': SECRET}
        options.update(overrides)
        return LiveDataThread(queue.Queue(), **options)

    def test_it_matches_what_the_far_end_computes(self):
        """The PHP does hash_hmac('sha256', $stamp . $body, $SECRET)."""
        body = b'{"a":1}'
        stamp = '1788000000'

        mine = self.thread().signature(stamp, body)
        theirs = hmac.new(SECRET.encode(), stamp.encode() + body,
                          hashlib.sha256).hexdigest()

        assert mine == theirs

    def test_a_changed_body_changes_it(self):
        thread = self.thread()
        stamp = '1788000000'

        assert thread.signature(stamp, b'{"a":1}') != thread.signature(stamp, b'{"a":2}')

    def test_a_changed_timestamp_changes_it(self):
        """This is what stops a captured post from being sent again."""
        thread = self.thread()
        body = b'{"a":1}'

        assert thread.signature('1788000000', body) != thread.signature('1788000060', body)

    def test_a_different_secret_changes_it(self):
        body, stamp = b'{"a":1}', '1788000000'

        assert (self.thread().signature(stamp, body)
                != self.thread(secret='0000').signature(stamp, body))


class TestWhatGoesOverTheWire:

    def test_the_post_carries_both_headers_and_the_json(self):
        thread = LiveDataThread(queue.Queue(), server_url='https://example.com/live.php',
                                secret=SECRET, skip_upload=True)
        sent = {}

        def capture(request, data=None):
            sent['request'] = request
            sent['data'] = data

        thread.post_with_retries = capture
        thread.skip_upload = False
        payload = {'dateTime': NOW, 'usUnits': weewx.US, 'current': {'outTemp': 20.0},
                   'day': {}}

        thread.process_record(payload, None)

        assert json.loads(sent['data'].decode()) == payload
        headers = sent['request'].headers
        # urllib title-cases header names.
        assert headers['X-timestamp']
        assert len(headers['X-signature']) == 64

    def test_skip_upload_stops_before_the_post(self):
        thread = LiveDataThread(queue.Queue(), server_url='https://example.com/live.php',
                                secret=SECRET, skip_upload=True)

        with pytest.raises(weewx.restx.AbortedPost):
            thread.process_record({'dateTime': NOW}, None)
