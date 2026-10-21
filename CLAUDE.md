# weewx-livedata

WeeWX service and PHP endpoint for publishing live readings as a static JSON file.

## Structure

* `install.py` registers files, services and configuration defaults with WeeWX.
* `bin/user/livedata.py` collects readings, posts signed JSON and generates the
  endpoint from the template in `skins/LiveData/`.
* `live.php` checks requests and writes `live.json` on the web host.
* `tests/` covers the installer, service and PHP endpoint.

## Conventions

Python follows WeeWX's style, with types in Google docstrings and no runtime
annotations. Keep the PHP endpoint and Python signing code compatible.

## Tests

Run `just fast` with WeeWX's dependencies installed and its Python executable on
`PATH`. When using a WeeWX checkout, set `PYTHONPATH=/path/to/weewx/src`.
Endpoint tests require `php` on `PATH`; otherwise pytest skips them.
The local suite took about two seconds with PHP 8.3 in Docker.
