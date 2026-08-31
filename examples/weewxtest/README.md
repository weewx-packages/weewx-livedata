# A page with no skin

A single HTML file that shows a station's current readings, its charts, and the
figures of its whole record. It has no templates behind it and nothing is
rendered into it. Every number on it arrives as JSON, written by WeeWX:

| File | Written by | How often |
|---|---|---|
| `live.json` | this extension | every 10 seconds |
| `data/index.json`, `data/archive/…` | `weewx.jsongenerator` | every archive interval |
| `records.json` | a Cheetah template | once a day |
| `lang/de/lang.json`, `lang/en/lang.json` | a Cheetah template | every archive interval |

The point of the example is what that combination makes possible. The page is a
static file on a web host. It can be moved, cached, or rewritten in another
framework, and none of that touches WeeWX. Switching it between German and
American units changes no file on the server: the reader picks another
`lang.json`, and the conversion table in `index.json` does the rest.

Running: <https://evoftp.fs-sys.de/weewxtest/>

Why any of it is worth doing this way is on the wiki, under
[A page with no skin](https://github.com/hilman2/weewx-livedata/wiki/A-page-with-no-skin).

## What it shows

**Current readings**, with the age of the last one counting up beside them, and
today's high and low. From `live.json`.

**Four charts** over a day, week, month or year, with arrows to step backwards.
From the JSON generator's archive files. Rain and evaporation share a chart and
are drawn as bars, cumulated into a bucket that suits the span.

**The whole record**: what this year has had, what it lost to evaporation, and
the difference. Then the wettest year, month and day, and the highest and lowest
temperature. From `records.json`.

**A language switch**, German or American. It changes the words, the units, the
number format, the date format, and where a week starts.

## Setting it up

Three reports and two skins. Neither skin has a line of HTML in it.

Copy `skins/LiveTestRecords` and `skins/LiveTestLang` into your `skins`
directory, put `index.html` where the reports write, and add to `weewx.conf`:

``` ini
[StdReport]

    # The charts and the unit tables. Any skin carrying a [JSONGenerator]
    # section will do; this one borrows Horizon's.
    [[LiveTestData]]
        skin = Horizon
        HTML_ROOT = public_html/weewxtest
        [[[Generators]]]
            generator_list = weewx.jsongenerator.JSONGenerator
        [[[JSONGenerator]]]
            periods = true
            [[[[Archive]]]]
                enable = true

    # The figures of the whole record.
    [[LiveTestRecords]]
        skin = LiveTestRecords
        HTML_ROOT = public_html/weewxtest

    # One report per language, each into its own directory. This is what lets
    # the page offer two: a report renders in one language and one unit system,
    # so two reports give two files to choose between.
    [[LiveTestLangDe]]
        skin = LiveTestLang
        lang = de
        unit_system = metricwx
        HTML_ROOT = public_html/weewxtest/lang/de

    [[LiveTestLangEn]]
        skin = LiveTestLang
        lang = en
        unit_system = us
        HTML_ROOT = public_html/weewxtest/lang/en
```

`index.html` and `live.php` are not written by any report, so put them in
`HTML_ROOT` by hand. The FTP or rsync report carries them up with the rest.

## Where the aggregates come from

`records.json.tmpl` is a Cheetah template that writes JSON instead of HTML. It
needs no generator of its own, because a template can answer anything a report
tag can answer:

```
#if $span.rain.sum.raw is not None
#silent $found.__setitem__('rain_sum', $span.rain.sum.raw)
#end if
```

It writes one row per month for the whole record, and one row per day for the
current year. Not answers, numbers. Which month was the wettest is worked out in
the browser, so a page can ask a question WeeWX was never told about without
anything being regenerated.

Months are cheap: fourteen years is 168 rows. Days are not, so only the current
year carries them. That is the span where a single day is still worth naming.

One query per figure per row is slow, so `stale_age = 86400` in the skin holds
the template to once a day. A month that has ended never changes again.

Evaporation costs no sensor. WeeWX computes `ET` in `StdWXCalculate` from
radiation, temperature, humidity and wind, and it is a column in the archive
like any other.

## Notes

The page is one file with no build step and no dependencies but `echarts.min.js`,
which sits beside it. It is written in ES5 so that an old tablet on a windowsill
can display it.

`data-obs` markup is not used here. The page draws its own rows, so it maps
observations to elements itself. A skin that already carries `data-obs` needs
only the fetch shown in the main README.
