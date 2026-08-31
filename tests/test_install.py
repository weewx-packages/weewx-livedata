#
#    Copyright (c) 2026 Manuel Hilgert
#
#    See the file LICENSE.txt for your rights.
#
"""The installer, which has to get the key into both halves or neither.

Run with:

    PYTHONPATH=bin:/path/to/weewx/src pytest tests/
"""

import io
import os
import shutil
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

pytest.importorskip('weecfg.extension', reason="needs weewx on the path")

from install import ANCHOR, LiveDataInstaller, _write_secret  # noqa: E402


@pytest.fixture
def unpacked(tmp_path):
    """A copy of live.php, the way weectl leaves one after unpacking.

    Yields:
        str: The directory holding it.
    """
    shutil.copy(os.path.join(ROOT, 'live.php'), str(tmp_path))
    return str(tmp_path)


def php(where):
    return io.open(os.path.join(where, 'live.php'), encoding='utf-8').read()


def test_the_key_reaches_the_configuration_and_the_file(unpacked):
    """Both halves sign with it, so both halves have to have it."""
    installer = LiveDataInstaller(here=unpacked)

    secret = installer['config']['StdRESTful']['LiveData']['secret']
    assert len(secret) == 32
    assert ("$SECRET   = '%s';" % secret) in php(unpacked)
    assert ANCHOR not in php(unpacked)


def test_two_installs_do_not_get_two_keys(unpacked):
    """The second would leave the station signing with a key the host lacks."""
    first = LiveDataInstaller(here=unpacked)
    written = php(unpacked)

    LiveDataInstaller(here=unpacked)

    assert php(unpacked) == written
    assert first['config']['StdRESTful']['LiveData']['secret'] in written


def test_every_install_gets_its_own_key(tmp_path):
    """Two stations must not end up able to post to each other's endpoint."""
    one, two = str(tmp_path / 'one'), str(tmp_path / 'two')
    for where in (one, two):
        os.makedirs(where)
        shutil.copy(os.path.join(ROOT, 'live.php'), where)

    assert (LiveDataInstaller(here=one)['config']['StdRESTful']['LiveData']['secret']
            != LiveDataInstaller(here=two)['config']['StdRESTful']['LiveData']['secret'])


def test_it_registers_the_service_where_the_engine_looks(unpacked):
    installer = LiveDataInstaller(here=unpacked)

    assert installer['restful_services'] == 'user.livedata.StdLiveData'


def test_the_repository_copy_still_holds_the_anchor():
    """The installer rewrites what weectl unpacked, never the checkout."""
    assert ANCHOR in io.open(os.path.join(ROOT, 'live.php'), encoding='utf-8').read()


def test_a_file_without_the_anchor_is_left_alone(unpacked):
    path = os.path.join(unpacked, 'live.php')
    io.open(path, 'w', encoding='utf-8', newline='\n').write("<?php\n# nothing to replace\n")

    _write_secret('deadbeef', unpacked)

    assert php(unpacked) == "<?php\n# nothing to replace\n"
