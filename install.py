#
#    Copyright (c) 2026 Manuel Hilgert
#
#    See the file LICENSE.txt for your rights.
#
"""Install the posting service and the report that generates its PHP endpoint."""

import secrets

from weecfg.extension import ExtensionInstaller

VERSION = "0.2.1"


def loader():
    """Return the installer expected by weectl.

    Returns:
        LiveDataInstaller: The extension's files and configuration defaults.
    """
    return LiveDataInstaller()


class LiveDataInstaller(ExtensionInstaller):
    """Register the service, endpoint template and report with WeeWX."""

    def __init__(self):
        """Provide a new station key as a default, preserving existing settings."""
        secret = secrets.token_hex(16)
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
                },
                'StdReport': {
                    'LiveData': {'skin': 'LiveData', 'enable': 'true'}
                },
            },
            files=[('bin/user', ['bin/user/livedata.py']),
                   ('skins/LiveData', ['live.php', 'skins/LiveData/skin.conf'])]
        )
