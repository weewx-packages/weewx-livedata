---
name: weewx-json-frontend
description: "Build a weather front end on the JSON that WeeWX writes: the archive from weewx.jsongenerator, live readings from weewx-livedata, and aggregates from a Cheetah template. Load this before writing a page, a widget or a plugin that shows WeeWX data, and before writing a Cheetah template that emits JSON. Carries the exact file formats, the aggregate patterns, and the failure modes that are silent."
user-invocable: true
allowed-tools: Read, Write, Edit, Bash, Grep, Glob
---

# A front end on WeeWX's JSON

WeeWX can be a data source rather than a renderer of HTML. Three producers write
JSON, and anything that can fetch a URL can consume it.

| Producer | Writes | Needs |
|---|---|---|
| `weewx.jsongenerator` | the archive, one day to the whole record | WeeWX 5.6 |
| a Cheetah template | any figure you name | WeeWX, any version |
| `weewx-livedata` | the current readings, every few seconds | the extension |

The first two are WeeWX. The third is
<https://github.com/hilman2/weewx-livedata>.

## Read the source before writing against it

Do not infer a format. These are the files that define them:

| Question | Read |
|---|---|
| What the JSON generator writes | `src/weewx/jsongenerator.py` in the WeeWX repo |
| What tags a template can use | `src/weewx/tags.py`, classes `TimeBinder` and `TimespanBinder` |
| What `.raw` means | `src/weewx/units.py`, class `ValueHelper` |
| What helpers a template has | `src/weewx/cheetahgenerator.py`, `default_search_list` |
| What aggregates exist | `docs_src/reference/aggtypes.md` |
| What the live file holds | `bin/user/livedata.py`, method `_payload` |

WeeWX 5.6 lives on the `development` branch until it is released:

```bash
git clone -b development https://github.com/weewx/weewx.git
```

An installed WeeWX has the same files under its `src` directory. Find it with
`weectl --version` and `python3 -c "import weewx; print(weewx.__file__)"`.

## The formats

### `data/index.json`

The unit tables, and what plots exist.

```
units.groups[obs]              -> "group_temperature"
units.report[group]            -> "degree_C"     what this report renders in
units.systems[SYS][group]      -> "degree_F"     SYS is "US"|"METRIC"|"METRICWX"
units.convert[from][to]        -> [factor, offset]
units.labels[unit]             -> "°C"
units.formats[unit]            -> "%.1f"
plots[]                        -> {name, group, title, unit, unit_label, obs_types}
```

Conversion is `value * factor + offset`. Nothing else.

### `data/<plot>.json`, the period files

Off unless `periods = true`. One plot over one span, ending now.

```
{name, generated, start, stop, x_interval, yscale, aggregate_interval,
 unit, unit_label, daynight,
 series: [{obs_type, label, plot_type, unit, unit_label, color,
           time: [...], values: [...]}]}
```

`time` and `values` are parallel arrays, not pairs.

### `data/archive/index.json`

```
{interval, fine_interval, first, last, rebuilt,
 groups: [{name, title, unit_label, years: [2026],
           covered: {"2026": ts}, intervals: {"2026": 3600},
           fine: {...}, fine_intervals: {"2026-08": 900},
           raw: {...}, raw_intervals: {"2026-08-31": 60}}]}
```

`groups` is a **list**, not an object. The file names follow from the keys:

```
<group>-<YYYY>.json             <group>-fine-<YYYY-MM>.json
<group>-raw-<YYYY-MM-DD>.json
```

### `data/archive/<file>.json`

```
{name, start, interval, count, covered, resume_ts, resume_slot,
 yscale, unit, unit_label,
 series: [{obs_type, label, aggregate_type, color, values: [...]}]}
```

**No timestamps.** The reading at index `i` was taken at
`start + i * interval`. `null` means no reading, not zero.

### `live.json`

```
{dateTime, usUnits, current: {obs: raw_value},
 day: {obs: {min, max}}}
```

`usUnits` is `1` US, `16` METRIC, `17` METRICWX. Values are **raw, in the
station's unit system**, not the report's. An observation absent from `current`
has not reported for sixteen minutes: show it as unavailable, never as zero.

## Writing aggregates

A Cheetah template can write JSON. This is the whole mechanism, and it needs no
generator, no Python and no extension.

```
#errorCatcher Echo
#encoding UTF-8
#set $out = {'units': {}, 'months': {}}
#silent $out['units'].update({'rain': $getVar('unit.unit_type.rain')})
#for $y in $alltime.years
#for $m in $y.months
#if $m.rain.sum.raw is not None
#silent $out['months'].__setitem__($m.dateTime.format("%Y-%m"),
                                   {'rain_sum': $m.rain.sum.raw})
#end if
#end for
#end for
$jsonize($out)
```

Spans: `$current $latest $hour $day $yesterday $week $month $year $rainyear
$alltime $span(day_delta=30)`.

Each yields smaller ones: `.years .months .days .hours .seasons .records
.spans(interval=3600)`.

Aggregates: `avg count diff first firsttime last lasttime max maxtime min
mintime sum rms not_null exists has_data gustdir vecavg vecdir tderiv maxmin
maxmintime minmax minmaxtime meanmax meanmin maxsum maxsumtime minsum minsumtime
avg_ge(vt) avg_le(vt) max_ge(vt) max_le(vt) min_ge(vt) min_le(vt) sum_ge(vt)
sum_le(vt)`.

The `_ge`/`_le` family counts **days** and takes a `ValueTuple`:

```
$year.outTemp.min_le((0, 'degree_C', 'group_temperature'))    frost days
```

### Rules that are not optional

**Write `.raw`, and say which unit.** `.raw` is already in the report's unit.
Without `$getVar('unit.unit_type.<obs>')` beside it the number is meaningless.

**Write numbers, not answers.** Rows per month, not "the wettest month". The
browser picks. This is what lets a page ask a question the template was never
told about.

**Never name a loop variable after a tag.** `#for $year in $alltime.years`
shadows `$year` for the rest of the file, and a later `$year.days` then iterates
the wrong span. Silent, and expensive to find. Use `$y`, `$m`, `$d`.

**`#silent $out.__setitem__(k, v)`,** because `$out[k] = v` is not Cheetah.

**Guard every figure with `is not None`,** or the file fills with nulls and the
page has four things to test instead of one.

**Set `stale_age`** on any template that loops over the record. One query per
figure per row, on every report cycle otherwise.

**Size the file.** Months for the whole record is cheap, about 12 rows a year.
Days for the whole record is not. Write days only for the current year.

### Wiring

`skins/<Name>/skin.conf`:

```ini
[CheetahGenerator]
    encoding = utf8
    [[ToDate]]
        [[[records]]]
            template = records.json.tmpl
            stale_age = 86400
[Generators]
    generator_list = weewx.cheetahgenerator.CheetahGenerator
```

`weewx.conf`:

```ini
[StdReport]
    [[MyFigures]]
        skin = <Name>
        HTML_ROOT = public_html/weather
```

**Edit `weewx.conf` with `configobj`, never with `sed`.** A value holding a
comma is quoted, and a naive edit corrupts it.

## Writing the page

```js
const SYSTEM = {1: 'US', 16: 'METRIC', 17: 'METRICWX'};

function convert(U, value, from, to) {
  if (!from || !to || from === to) return value;
  const steps = U.convert[from] && U.convert[from][to];
  return steps ? value * steps[0] + steps[1] : null;
}

/* A live reading in the unit the report renders in. */
function reading(U, live, obs) {
  const group = U.groups[obs];
  const system = U.systems[SYSTEM[live.usUnits]];
  const from = group && system && system[group];
  const to = group && U.report[group];
  if (live.current[obs] === undefined || !from || !to) return null;
  return {value: convert(U, live.current[obs], from, to), unit: to};
}
```

Poll `live.json` every 10 s with `cache: 'no-store'`, skip a payload whose
`dateTime` is not newer, and re-poll on `visibilitychange`.

For charts, pick an archive tier by point count. The finest tier whose spacing
keeps `(to - from) / spacing` under about 20,000, falling back to the coarsest
so a window always gets something. A year at the raw grid is 525,600 points.

Sum totals (rain, ET) into buckets and draw bars. A line through a total draws a
floor between showers.

Step windows on the calendar, not in seconds: `Date.setDate/setMonth/setFullYear`.
A day of 86,400 seconds ending at a moving point puts one afternoon next to
another and drifts across a clock change.

## Verify, do not assume

```bash
weectl report run                       # render everything now
python3 -m json.tool <file>             # is it JSON at all
```

`#errorCatcher Echo` turns an unknown name into an empty string and an unknown
attribute into a bare `.attr`, logging nothing. The only trace is a key with no
value:

```json
{"generated": , "rain": 63.8}
```

Grep the output for `: ,` and `: }`. When a template misbehaves, take the error
catcher out, render, and put it back.

Cross-check any figure two ways before believing it. Summing the day rows and
reading the month row must agree; if they do not, the template is wrong.

## Do not

* Hard code observation labels. Write them out of a report, one file per
  language, and fetch the one you want.
* Format numbers in the template. Raw numbers plus the tables serve every reader
  at once.
* Cache `live.json`. Fixed URL, changing content, and a cached copy freezes the
  page for everyone but the first reader.
* Treat `null` in an archive file as zero.
* Assume the archive index `groups` is keyed by name. It is a list.
