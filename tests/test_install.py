#
#    Copyright (c) 2026 Manuel Hilgert
#
#    See the file LICENSE.txt for your rights.
#
"""Installer defaults and endpoint generation, without mutating the payload."""

import os
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

pytest.importorskip('weecfg.extension', reason="needs weewx on the path")

from install import LiveDataInstaller  # noqa: E402
from user.livedata import write_endpoint  # noqa: E402


def test_installer_provides_a_station_key():
    secret = LiveDataInstaller()['config']['StdRESTful']['LiveData']['secret']

    assert len(bytes.fromhex(secret)) == 16


def test_every_station_gets_its_own_default_key():
    one, two = LiveDataInstaller(), LiveDataInstaller()

    assert (one['config']['StdRESTful']['LiveData']['secret']
            != two['config']['StdRESTful']['LiveData']['secret'])


def test_it_registers_the_service_and_report():
    installer = LiveDataInstaller()

    assert installer['restful_services'] == 'user.livedata.StdLiveData'
    assert installer['config']['StdReport']['LiveData']['skin'] == 'LiveData'


def test_loading_the_installer_does_not_mutate_the_template():
    template = ROOT / 'live.php'
    original = template.read_bytes()

    LiveDataInstaller()
    LiveDataInstaller()

    assert template.read_bytes() == original
    assert b"$SECRET   = 'replace_me';" in original


@pytest.mark.parametrize('template,secret', [
    ('<?php\n# missing placeholder\n', 'valid-key'),
    ("$SECRET   = 'replace_me';", ''),
    ("$SECRET   = 'replace_me';", 'replace_me'),
    ("$SECRET   = 'replace_me';" * 2, 'valid-key'),
])
def test_invalid_inputs_leave_the_existing_endpoint_intact(tmp_path, template, secret):
    source = tmp_path / 'template.php'
    source.write_text(template)
    endpoint = tmp_path / 'live.php'
    endpoint.write_text('existing endpoint')

    with pytest.raises(ValueError):
        write_endpoint(str(source), str(endpoint), secret)

    assert endpoint.read_text() == 'existing endpoint'


def test_generated_endpoint_is_readable_by_the_web_server(tmp_path):
    endpoint = tmp_path / 'web' / 'live.php'

    write_endpoint(str(ROOT / 'live.php'), str(endpoint), 'a-station-key')

    assert os.stat(str(endpoint)).st_mode & 0o777 == 0o644
    assert list(endpoint.parent.iterdir()) == [endpoint]
