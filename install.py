#
#    Copyright (c) 2026 Manuel Hilgert
#
#    See the file LICENSE.txt for your rights.
#
"""Installer for weewx-livedata.

Writes a fresh secret into weewx.conf and into the copy of live.php that goes
next to the reports. Nobody has to type it anywhere: the file is uploaded with
everything else the next time the report runs.
"""

import os
import secrets

from weecfg.extension import ExtensionInstaller

VERSION = "0.1.0"


def loader():
    return LiveDataInstaller()


class LiveDataInstaller(ExtensionInstaller):
    def __init__(self, here=None):
        """Build the installer, and put a fresh key in the copy of live.php.

        Writing to the file is a side effect of building this object, because
        that is the only moment the installer gets before weectl copies the
        files. It rewrites the copy weectl unpacked, not anything in a checkout.

        Args:
            here (str|None): The directory holding live.php. Defaults to the one
                this file is in, which is where weectl unpacked it.
        """
        secret = secrets.token_hex(16)
        _write_secret(secret, here)
        super(LiveDataInstaller, self).__init__(
            version=VERSION,
            name='livedata',
            description='Post the current readings to a web host, for pages that'
                        ' WeeWX did not render.',
            author="Manuel Hilgert",
            restful_services='user.livedata.StdLiveData',
            config={
                'StdRESTful': {
                    'LiveData': {
                        'url': 'replace_me',
                        'secret': secret,
                        'post_interval': '10',
                        'extremes': 'outTemp, windSpeed, windGust, barometer, rain',
                    }
                }
            },
            files=[('bin/user', ['bin/user/livedata.py']),
                   ('public_html', ['live.php'])]
        )


ANCHOR = "$SECRET   = 'replace_me';"


def _write_secret(secret, here=None):
    """Put the same secret in the copy of live.php that will be installed.

    The station and the host have to agree on it, and the file is the only place
    the host learns it. Doing this at install time means the two halves cannot
    drift apart, and that whoever installs never sees the key at all.

    A file that no longer holds the anchor has been through this once already,
    and is left as it is: installing twice would otherwise leave the station
    signing with a key the host does not have.

    Args:
        secret (str): The key, as hex.
        here (str|None): The directory holding live.php. Defaults to the one this
            file is in.
    """
    path = os.path.join(here or os.path.dirname(os.path.abspath(__file__)), 'live.php')
    with open(path, encoding='utf-8') as fd:
        text = fd.read()
    if ANCHOR not in text:
        return
    with open(path, 'w', encoding='utf-8') as fd:
        fd.write(text.replace(ANCHOR, "$SECRET   = '%s';" % secret, 1))
