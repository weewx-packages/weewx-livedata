# weewx-livedata

Puts the current readings on a web page as fast as your station reports them,
without MQTT and without opening a port at home.

WeeWX writes its reports once per archive interval, usually every five minutes.
A page that shows a reading older than that is the normal state of affairs. This
service watches LOOP packets instead, keeps the latest value of every
observation, and posts the lot to your web space every few seconds. A small file
there receives it and writes `live.json` next to your pages, and the page reads
that file.

The station posts outward. It needs no open port, no fixed address and no
dynamic DNS, which is what stops most live setups on a home connection.

The [wiki](https://github.com/hilman2/weewx-livedata/wiki) says how it works,
what a replacement endpoint has to do, and
what a page built entirely on WeeWX's JSON looks like.

## What it needs

* WeeWX 5.2 or later
* Somewhere to put `live.php`, on a host that runs PHP over HTTPS

Any other language will do instead. `live.php` is forty lines, and the section
[The endpoint](#the-endpoint) says what a replacement has to do.

## Installing

```
weectl extension install https://github.com/hilman2/weewx-livedata/archive/master.zip
```

The installer writes a fresh key into `weewx.conf` and into its copy of
`live.php`. Nobody has to type it anywhere.

Then set the URL you will put `live.php` at:

``` ini
[StdRESTful]
    [[LiveData]]
        url = https://example.com/live.php
```

`live.php` is installed into `public_html`, so the FTP or rsync report carries
it
up with everything else on its next run. If you publish some other way, copy it
across yourself, and keep the copy the installer wrote: it holds the key.

Restart WeeWX. Within a minute `live.json` should appear beside it.

## Options

All of them go under `[StdRESTful] [[LiveData]]`.

#### url

Where to post. Required. Use `https` where the host offers it.

#### secret

The key both ends sign with. Written by the installer. It never travels over the
wire, and changing it means changing `live.php` to match.

#### post_interval

Seconds to leave between posts. Default is `10`. Every LOOP packet is watched
whatever this says, so a lower number costs your web space, not your station.
What it costs is worked out in [How it
works](https://github.com/hilman2/weewx-livedata/wiki/How-it-works).

#### extremes

Which readings also carry their high and low for the day. Default is
`outTemp, windSpeed, windGust, barometer, rain`. Set it to nothing to leave them
out.

Each name costs two queries against the daily summaries per archive record.
Between records the extremes are raised from LOOP packets, so a high that has
just been reached is in the file at once.

#### data_binding

Which database the extremes are read from. Default is `wx_binding`.

## What is in the file

``` json
{
  "dateTime": 1788000000,
  "usUnits": 1,
  "current": {"outTemp": 68.4, "windSpeed": 5.2, "barometer": 30.02},
  "day": {"outTemp": {"min": 51.1, "max": 71.8}}
}
```

Raw values in the unit system the station measures in, not formatted text, so
one file serves every report of the station whatever units and language each of
them renders in.

`current` holds the last value seen for each observation, which is not the same
as the last packet. A reading that has not arrived for sixteen minutes is left
out altogether, which lets a page tell "no such sensor" from "not reporting".

`day` holds the high and low so far today, for the observations named in
`extremes`.

`dateTime` is when the readings were taken. Compare it against the clock to say
that a station has gone quiet.

Why it is shaped this way is in [How it
works](https://github.com/hilman2/weewx-livedata/wiki/How-it-works).

## The endpoint

`live.php` checks the signature, checks the age, checks that the body parses as
JSON, and writes it out. The station never sends the key. It sends

```
X-Timestamp: 1788000000
X-Signature: HMAC-SHA256(secret, timestamp + body)
```

and the endpoint recomputes the signature. A post that somebody captured cannot
be sent again once its timestamp has aged past two minutes.

**Check that your host actually executes `.php`.** Where it does not, it serves
the file as text and the key is on the open web. Fetching the URL in a browser
should give you `POST only`, not source code.

To write one in another language, see
[The endpoint
contract](https://github.com/hilman2/weewx-livedata/wiki/The-endpoint-contract).

## Using it from a page

Each reading is one key. A page that already marks its readings the way the
Horizon skin does needs nothing but the fetch:

``` html
<span data-obs="outTemp" data-value="68.4" data-unit="degree_F">68.4</span>
```

``` js
setInterval(async () => {
  const live = await (await fetch('live.json', {cache: 'no-store'})).json();
  for (const [obs, value] of Object.entries(live.current)) {
    document.querySelectorAll('[data-obs="' + obs + '"]').forEach(el => {
      el.dataset.value = value;
      el.textContent = value.toFixed(1);
    });
  }
}, 10000);
```

That last line puts the raw number on the page. Converting it into the unit the
reader asked for is the job of the table in `index.json`.

## A worked example

[`examples/weewxtest`](examples/weewxtest) is a static page with no skin behind
it: current readings, charts, the figures of the whole record, and a switch
between German and American units, all of it fed by JSON that WeeWX writes.
What that makes possible is in
[A page with no
skin](https://github.com/hilman2/weewx-livedata/wiki/A-page-with-no-skin).

## Tests

```
PYTHONPATH=bin:/path/to/weewx/src pytest tests/
```

The endpoint tests run `live.php` under PHP's built-in server and post to it,
because in CLI `php://input` is not connected to standard input and a command
line harness would prove nothing about the path a real request takes. They skip
themselves where there is no `php`.

## Licence

GPL 3, the same as WeeWX.
