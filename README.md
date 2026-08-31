# weewx-livedata

Makes a WeeWX station a data source, so the page that shows it can be anything
you want to build.

WeeWX renders HTML. Changing what a page looks like means editing Cheetah
templates, and changing what it shows means editing them again. For a skin that
is the right arrangement. It is in the way as soon as the weather is one part of
a site that already exists, or the page should be a WordPress widget, a React
dashboard, or a screen on a tablet in the hall.

Three pieces together take it out of the way. None of them renders markup:

| Source | Writes | Comes from |
|---|---|---|
| `weewx.jsongenerator` | the archive as JSON, one day to the whole record | WeeWX 5.6 |
| a Cheetah template | whatever figures you name, as JSON | WeeWX, any version |
| this extension | the current readings, every few seconds | here |

What comes out is a directory of static JSON files beside your pages. Your front
end fetches them. That is the whole interface.

## What that buys

**Any stack.** `fetch` and `json_decode` exist everywhere. A plain HTML page, a
PHP include in an existing site, a WordPress plugin, a Node or Astro build, a
Vue component: none of them needs to know that WeeWX exists, only that some JSON
sits at a URL.

**Static files.** No PHP execution to draw a page, no database query per
visitor, nothing to keep running. They cache, they go behind a CDN, they survive
a WeeWX restart, and a station that goes offline leaves the last state readable
instead of a broken page.

**No Cheetah for the ordinary case.** Live readings and charts over any span
back to the beginning of the record need none: those files are already written.
Cheetah comes in only where you want a figure nobody has computed yet, and
[Aggregates with Cheetah](https://github.com/hilman2/weewx-livedata/wiki/Aggregates-with-Cheetah) is a guide to that with
templates to copy.

**Units and language stay open.** The files hold raw numbers, not formatted
text, with the conversion table beside them. One set of files serves a metric
page and a US page, and a reader can switch between them without a report being
re-rendered.

**One page, one file.** The starter theme below is a single HTML file: live
readings, charts over four spans with archive navigation, aggregates, and a
language switch. Copy it and restyle it.

## Where to start

| You want to | Read |
|---|---|
| Put live readings on a page you already have | [Installing](#installing), then [Using it from a page](#using-it-from-a-page) |
| Build a whole page on WeeWX's JSON | [Building a page on WeeWX](https://github.com/hilman2/weewx-livedata/wiki/Building-a-page-on-WeeWX) |
| Compute a figure WeeWX does not already write | [Aggregates with Cheetah](https://github.com/hilman2/weewx-livedata/wiki/Aggregates-with-Cheetah) |
| Put it inside WordPress, Node, or a PHP site | [Integrating into an existing site](https://github.com/hilman2/weewx-livedata/wiki/Integrating-into-an-existing-site) |
| Copy a working page and restyle it | [The starter theme](https://github.com/hilman2/weewx-livedata/wiki/The-starter-theme) |
| Know how the live part works | [How it works](https://github.com/hilman2/weewx-livedata/wiki/How-it-works) |
| Write the endpoint in another language | [The endpoint contract](https://github.com/hilman2/weewx-livedata/wiki/The-endpoint-contract) |

## What this extension does

The other two pieces are WeeWX. This one is the live reading.

WeeWX writes its reports once per archive interval, usually every five minutes,
so a page built by a report shows a reading up to five minutes old. This service
watches LOOP packets instead, keeps the latest value of every observation, and
posts the lot to your web space every few seconds. A small file there receives
it and writes `live.json` next to your pages.

The station posts outward. It needs no open port, no fixed address and no
dynamic DNS, which is what stops most live setups on a home connection.

## What it needs

For the live readings:

* WeeWX 5.2 or later
* Somewhere to put `live.php`, on a host that runs PHP over HTTPS

Any other language will do instead of PHP. `live.php` is forty lines, and
[The endpoint contract](https://github.com/hilman2/weewx-livedata/wiki/The-endpoint-contract) says what a replacement has to
do.

For the archive and the charts:

* WeeWX 5.6, which is where `weewx.jsongenerator` and the `Horizon` skin arrive.
  Until it is released it is on the `development` branch.

The two are independent. Live readings work on 5.2 with no JSON generator, and
the JSON generator works with no live extension. Together they cover a page.

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

## The starter theme

[`examples/weewxtest`](examples/weewxtest) is a working page to copy: current
readings with today's range, four charts with archive navigation back to the
first record, the figures of the whole record, and a switch between German and
American units. One HTML file, one copy of ECharts, no build step, no framework.

Everything on it comes from the JSON. Restyling it is CSS, and swapping in your
own charts is one list at the top of the script.

[The starter theme](https://github.com/hilman2/weewx-livedata/wiki/The-starter-theme) walks through it.

## For an agent

[`skills/weewx-json-frontend`](skills/weewx-json-frontend) is a skill file for
Claude Code, Codex or anything that reads instructions from a repository. It
carries the file formats, the aggregate patterns, and where to read the WeeWX
source, so an agent can build the scaffolding without guessing at any of it.

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
