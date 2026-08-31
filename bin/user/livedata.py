#
#    Copyright (c) 2026 Manuel Hilgert
#
#    See the file LICENSE.txt for your rights.
#
"""Post the current readings to a web host, once every so many seconds.

A page that WeeWX did not render has no way to show a reading newer than the last
report. This service gives it one. It watches LOOP packets, keeps the latest
value of each observation, and posts the lot as JSON to a URL. Something at that
URL writes the body to a file, and the page fetches that file.

The direction matters more than it looks. The station posts outward, so it needs
no open port, no fixed address and no dynamic DNS, which is what stops most live
setups on a home connection.

To use it, add to weewx.conf:

    [StdRESTful]
        [[LiveData]]
            url = https://example.com/live.php
            secret = <32 hex characters, written by the installer>

            # How often to post, in seconds. Every LOOP packet is watched
            # whatever this says; only the posting is held back.
            post_interval = 10

            # Which readings also carry their high and low for the day. Each
            # name costs two queries against the daily summaries per archive
            # record.
            extremes = outTemp, windSpeed, windGust, barometer, rain

    [Engine]
        [[Services]]
            restful_services = ..., user.livedata.StdLiveData

The body is raw values with the unit system they were measured in, not formatted
text. A page converts them itself, from the table `weewx.jsongenerator` writes
into `index.json`. One file then serves every report of the station, whatever
units and language each of them renders in.
"""

import hashlib
import hmac
import json
import logging
import queue
import time
import urllib.request

import weedb
import weeutil.weeutil
import weewx
import weewx.manager
import weewx.restx
import weewx.xtypes

log = logging.getLogger(__name__)

VERSION = "0.1.0"


class StdLiveData(weewx.restx.StdRESTful):
    """Puts the current readings on the queue, once per LOOP packet.

    The engine thread does as little as possible here: update a dictionary, copy
    it, hand it over. Everything that can block, which is all of the network,
    happens in LiveDataThread.
    """

    def __init__(self, engine, config_dict):
        super().__init__(engine, config_dict)

        site_dict = weewx.restx.get_site_dict(config_dict, 'LiveData', 'url', 'secret')
        if site_dict is None:
            return

        # What steers this end. The rest goes to the thread.
        self.extremes = _as_list(site_dict.pop('extremes', None))
        binding = site_dict.pop('data_binding', 'wx_binding')
        # 'url' reads better in a configuration file than 'server_url', which is
        # what RESTThread calls it.
        site_dict['server_url'] = site_dict.pop('url')
        site_dict.setdefault('post_interval', 10)

        self.manager_dict = weewx.manager.get_manager_dict_from_config(config_dict, binding)

        # The last value seen for each observation, with the time it was seen. A
        # single LOOP packet is not a complete picture of the station: a Vantage
        # sends temperature in one packet and wind in the next, so a page fed
        # from raw packets would show readings appearing and disappearing.
        self.cache = weewx.restx.CachedValues()
        # The day's high and low for the observations named in 'extremes'. Read
        # from the database, then raised from LOOP packets between records.
        self.day = {}

        self.queue = queue.Queue()
        self.thread = LiveDataThread(self.queue, **site_dict)
        self.thread.start()

        self.bind(weewx.STARTUP, self.startup)
        self.bind(weewx.NEW_LOOP_PACKET, self.new_loop_packet)
        self.bind(weewx.NEW_ARCHIVE_RECORD, self.new_archive_record)

        log.info("LiveData: posting to %s every %s seconds",
                 site_dict['server_url'], site_dict['post_interval'])

    def startup(self, _unused):
        """Called when the engine is starting up. Read the day's extremes.

        Args:
            _unused (weewx.Event): Not used.
        """
        self._read_extremes()

    def new_loop_packet(self, event):
        """Called with every LOOP packet. Update the picture and offer it.

        The thread decides whether this one is posted. Deciding it here would
        mean keeping the time of the last post in two places.

        Args:
            event (weewx.Event): The event carrying the LOOP packet.
        """
        self.cache.update(event.packet, event.packet['dateTime'])
        self._raise_extremes(event.packet)
        self.queue.put(self._payload(event.packet['dateTime']))

    def new_archive_record(self, event):
        """Called when a record is archived. Read the day's extremes again.

        The daily summaries are current only as of the last record, so this is
        the moment they are worth reading. Between records the extremes are
        raised from LOOP packets, which is enough: a high that has just been
        reached is in the packet that reached it.

        Args:
            event (weewx.Event): The event carrying the new archive record.
        """
        self._read_extremes()

    def shutDown(self):
        """Tell the thread to finish what it holds, and stop."""
        if hasattr(self, 'thread') and self.thread.is_alive():
            self.queue.put(None)
            self.thread.join(20.0)
            if self.thread.is_alive():
                log.error("LiveData: unable to shut down thread")

    # ------------------------------------------------------------------ private

    def _payload(self, timestamp):
        """The whole picture, as it will be posted.

        Args:
            timestamp (int|float): The time of the packet that prompted this.

        Returns:
            dict: The readings, the day's extremes, and the unit system they are
                all measured in.
        """
        packet = self.cache.get_packet(int(timestamp))
        # None means the reading has gone stale. Leaving those out keeps the body
        # small, and lets a page tell "no such sensor" from "not reporting".
        current = {obs: value for obs, value in packet.items()
                   if value is not None and obs not in ('dateTime', 'usUnits')}
        return {
            'dateTime': int(timestamp),
            'usUnits': self.cache.unit_system,
            'current': current,
            'day': {obs: dict(pair) for obs, pair in self.day.items()},
        }

    def _read_extremes(self):
        """The day's high and low for each named observation, from the database."""
        if not self.extremes:
            return
        span = weeutil.weeutil.archiveDaySpan(time.time())
        try:
            with weewx.manager.open_manager(self.manager_dict) as manager:
                for obs in self.extremes:
                    self.day[obs] = {'min': _aggregate(manager, obs, span, 'min'),
                                     'max': _aggregate(manager, obs, span, 'max')}
        except (weewx.UnknownBinding, weedb.DatabaseError) as e:
            log.error("LiveData: cannot read the day's extremes: %s", e)

    def _raise_extremes(self, packet):
        """Move the day's high or low if this packet passed it.

        Args:
            packet (dict): A LOOP packet.
        """
        for obs, pair in self.day.items():
            value = packet.get(obs)
            if value is None:
                continue
            if pair['max'] is None or value > pair['max']:
                pair['max'] = value
            if pair['min'] is None or value < pair['min']:
                pair['min'] = value


class LiveDataThread(weewx.restx.RESTThread):
    """Signs a payload and posts it, off the engine thread.

    RESTThread already holds the queue, trims the backlog, keeps posts apart by
    'post_interval' and retries a failed one. What is added here is the signature
    and a JSON body in place of a query string.
    """

    def __init__(self,
                 q,
                 server_url,
                 secret,
                 protocol_name="LiveData",
                 post_interval=10,
                 max_backlog=1,
                 stale=60,
                 log_success=False,
                 log_failure=True,
                 timeout=10,
                 max_tries=3,
                 retry_wait=5,
                 skip_upload=False):
        """Initializer for LiveDataThread.

        Args:
            q (queue.Queue): Where the payloads appear.
            server_url (str): The URL to post to.
            secret (str): The key both ends sign with. Never sent.
            protocol_name (str): What to call this in the log.
            post_interval (int|float): Seconds to leave between posts.
            max_backlog (int): How many payloads may wait. One, because a payload
                that has been overtaken says nothing the next one does not.
            stale (int|float|None): Do not post a payload older than this.
            log_success (bool): Whether to log each successful post. Off by
                default: there are thousands of them a day.
            log_failure (bool): Whether to log a failed post.
            timeout (int|float): Seconds to wait on the socket.
            max_tries (int): How many times to try one payload.
            retry_wait (int|float): Seconds between tries.
            skip_upload (bool): True to do everything except the post.
        """
        super().__init__(q,
                         protocol_name=protocol_name,
                         post_interval=post_interval,
                         max_backlog=max_backlog,
                         stale=stale,
                         log_success=log_success,
                         log_failure=log_failure,
                         timeout=timeout,
                         max_tries=max_tries,
                         retry_wait=retry_wait,
                         skip_upload=skip_upload)
        self.server_url = server_url
        self.secret = secret.encode('utf-8')

    def process_record(self, record, dbmanager):
        """Sign the payload and post it.

        The inherited version queries the database to fill the record out and
        formats a URL from it. Neither applies: the payload is complete already,
        and it goes in the body.

        Args:
            record (dict): The payload, from StdLiveData._payload().
            dbmanager (weewx.manager.Manager|None): Not used.

        Raises:
            weewx.restx.AbortedPost: If 'skip_upload' is set.
        """
        body = json.dumps(record, separators=(',', ':')).encode('utf-8')
        stamp = str(int(time.time()))

        request = urllib.request.Request(self.server_url)
        request.add_header('User-Agent', 'weewx/%s' % weewx.__version__)
        request.add_header('Content-Type', 'application/json')
        request.add_header('X-Timestamp', stamp)
        request.add_header('X-Signature', self.signature(stamp, body))

        if self.skip_upload:
            raise weewx.restx.AbortedPost("Skip post")

        self.post_with_retries(request, body)

    def signature(self, stamp, body):
        """The signature for one post.

        The timestamp is part of what is signed, so a captured post cannot be
        sent again later: the far end refuses one whose timestamp has aged. The
        key itself never travels, which is what makes this hold on a host with no
        TLS.

        Args:
            stamp (str): The Unix time of this post, as a string.
            body (bytes): The body, exactly as it will be sent.

        Returns:
            str: The signature, as lowercase hex.
        """
        return hmac.new(self.secret, stamp.encode('utf-8') + body, hashlib.sha256).hexdigest()


def _as_list(value):
    """A configuration value as a list of names, however it was written.

    ConfigObj splits `a, b` into a list when it reads a bare line, but hands back
    one string when the line was quoted, which is how it writes a value that
    holds commas. A file people edit by hand carries both spellings and they mean
    the same thing.

    Getting this wrong is quiet and expensive: the whole string arrives as one
    observation name, and the query built from it fails with a SQL syntax error
    that says nothing about where it came from.

    Args:
        value (str|list[str]|None): What the option holds.

    Returns:
        list[str]: The names, trimmed, without the empty ones.
    """
    if value is None:
        return []
    if isinstance(value, str):
        value = value.split(',')
    return [str(name).strip() for name in value if str(name).strip()]


def _aggregate(manager, obs, span, kind):
    """One aggregate over one observation, or None where there is nothing.

    Args:
        manager (weewx.manager.Manager): An open manager.
        obs (str): The observation type, for example 'outTemp'.
        span (weeutil.weeutil.TimeSpan): The period to aggregate over.
        kind (str): The aggregation, for example 'min' or 'max'.

    Returns:
        int|float|None: The value, in the unit system the database holds.
    """
    try:
        value_t = weewx.xtypes.get_aggregate(obs, span, kind, manager)
    except (weewx.UnknownType, weewx.UnknownAggregation, weewx.CannotCalculate):
        return None
    return value_t[0]
