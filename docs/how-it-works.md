## Overview

This page explains the implementation and file format. For installation and
configuration, see the [README](../README.md).

The WeeWX service collects LOOP readings and sends them to `live.php`. The PHP
endpoint writes `live.json` beside your pages. A visitor reads that static file,
without running PHP or querying the station's database. The station initiates
the connection, so it does not need an incoming port or a fixed address.

## Where the readings come from

The service binds to `NEW_LOOP_PACKET`. Each packet updates a
`weewx.restx.CachedValues` cache and queues a snapshot for the posting thread.
The thread applies `post_interval`.

A LOOP packet can contain only some observations. The cache keeps the latest
value and timestamp for each observation, so a packet containing wind does not
remove a temperature reading from an earlier packet.

`CachedValues.get_packet()` uses a stale age of 960 seconds here. Values that
have not arrived for sixteen minutes are omitted from `current`. Observations
that have never arrived, or whose latest value is `None`, are also omitted.

## The live file

``` json
{
  "dateTime": 1788164045,
  "usUnits": 1,
  "current": {"outTemp": 68.2, "windSpeed": 0.0, "barometer": 30.008},
  "day": {"outTemp": {"min": 59.4, "max": 68.7}}
}
```

`dateTime` is the Unix timestamp, in seconds, of the LOOP packet that prompted
the snapshot. A page can compare it with the current time to show the age of the
readings. Individual observations can be older because they come from the
cache.

`usUnits` identifies the unit system of the LOOP readings. WeeWX uses `1` for
US, `16` for METRIC and `17` for METRICWX. `current` holds raw values in that
system, without labels or number formatting. For example, `outTemp` is in
Fahrenheit for US and Celsius for METRIC and METRICWX. The page chooses how to
convert and display the values.

An absent observation is unavailable. A value of zero is a valid reading.

`day` holds a `min` and `max` for each observation selected by `extremes`. Either
can be `null` when no value is available. With no observations selected, `day`
is an empty object.

## Daily extremes

The service reads the configured observations' daily minimum and maximum from
the database at startup and after each new archive record. The database binding
is selected with `data_binding`.

Between archive records, LOOP packets update the cached extremes when they
contain a new minimum or maximum. This lets a newly reached high appear in the
next post.

Each selected observation needs two aggregate queries per refresh. Setting
`extremes` empty disables these queries and the LOOP updates to daily extremes.

## Posting

`LiveDataThread` uses WeeWX's `RESTThread` to send requests outside the engine
thread. It applies the posting interval, trims queued snapshots when a backlog
builds up, and retries failed posts. The default `max_backlog` is `1`.

At the default ten-second interval, there can be 8,640 posts per day. A shorter
interval increases the number of PHP requests. Every LOOP packet updates the
cache regardless of the posting interval.

The service signs each request with the shared key. The
[endpoint contract](endpoint-contract.md) describes the headers and checks.

Each accepted post replaces `live.json`. The file contains the latest snapshot,
not a history of earlier posts. If the station stops posting, the file remains
readable with its last timestamp.
