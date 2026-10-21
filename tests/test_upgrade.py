#
#    Copyright (c) 2026 Manuel Hilgert
#
#    See the file LICENSE.txt for your rights.
#
"""Exercise fresh archives against an existing station, as an update does."""

import hashlib
import json
import pathlib
import shutil
import zipfile

import configobj
import pytest

import weecfg
from weecfg.extension import ExtensionEngine
from weewx.reportengine import StdReportEngine

ROOT = pathlib.Path(__file__).resolve().parents[1]


def station(tmp_path, html_root='public_html'):
    """Create an isolated station without enabled standard reports.

    Args:
        tmp_path (pathlib.Path): Parent directory for the station.
        html_root (str): Report output directory, relative to the station.

    Returns:
        configobj.ConfigObj: Station configuration, backed by weewx.conf.
    """
    path = tmp_path / 'station' / 'weewx.conf'
    path.parent.mkdir()
    template = pathlib.Path(weecfg.__file__).parents[1] / 'weewx_data' / 'weewx.conf'
    shutil.copyfile(str(template), str(path))
    config = configobj.ConfigObj(str(path), encoding='utf-8', interpolation=False)
    config['WEEWX_ROOT'] = str(path.parent)
    config['USER_ROOT'] = 'bin/user'
    config['StdReport']['HTML_ROOT'] = html_root
    for name in config['StdReport'].sections:
        if name != 'Defaults':
            config['StdReport'][name]['enable'] = 'false'
    config.write()
    (path.parent / 'bin' / 'user').mkdir(parents=True)
    (path.parent / 'bin' / 'user' / '__init__.py').write_text('')
    return weecfg.read_config(str(path))[1]


def install_fresh(config, destination):
    """Install a fresh copy and run enabled reports.

    Args:
        config (configobj.ConfigObj): Station configuration to update.
        destination (pathlib.Path): Directory for the unpacked extension.
    """
    shutil.copytree(str(ROOT), str(destination),
                    ignore=shutil.ignore_patterns('.git', '__pycache__', '.pytest_cache'))
    ExtensionEngine(config['config_path'], config).install_extension(str(destination), no_confirm=True)
    StdReportEngine(config, None).run()


def test_fresh_update_keeps_the_signing_key(tmp_path):
    """Updating from a new archive must preserve agreement with weewx.conf."""
    config = station(tmp_path)
    install_fresh(config, tmp_path / 'first')
    secret = config['StdRESTful']['LiveData']['secret']

    install_fresh(config, tmp_path / 'update')

    assert config['StdRESTful']['LiveData']['secret'] == secret
    endpoint = pathlib.Path(config['WEEWX_ROOT']) / 'public_html' / 'live.php'
    assert "$SECRET   = '%s';" % secret in endpoint.read_text(encoding='utf-8')


def test_endpoint_uses_the_configured_output_directory(tmp_path):
    config = station(tmp_path, html_root='weather-pages')

    install_fresh(config, tmp_path / 'source')

    assert (pathlib.Path(config['WEEWX_ROOT']) / 'weather-pages' / 'live.php').is_file()


def make_release(tmp_path, version):
    """Bundle the real payload with a test version for an isolated update.

    Args:
        tmp_path (pathlib.Path): Directory for the archive.
        version (str): Version advertised by the test installer and catalog.

    Returns:
        dict: Repository release metadata, including the archive digest.
    """
    archive = tmp_path / ('livedata-' + version + '.zip')
    paths = ['install.py', 'live.php', 'bin/user/livedata.py', 'skins/LiveData/skin.conf']
    with zipfile.ZipFile(str(archive), 'w') as bundle:
        for name in paths:
            text = (ROOT / name).read_text(encoding='utf-8')
            if name == 'install.py':
                from install import VERSION
                text = text.replace('VERSION = "%s"' % VERSION, 'VERSION = "%s"' % version)
            bundle.writestr('livedata/' + name, text)
    return {'version': version, 'requires_python': '>=3.7', 'requires_weewx': '>=5.2,<6',
            'archive': {'url': archive.as_uri(), 'format': 'zip',
                        'sha256': hashlib.sha256(archive.read_bytes()).hexdigest()},
            'restart_required': True}


def test_repository_install_and_update_preserve_the_endpoint_key(tmp_path):
    """The real payload must fit managed roots and keep its key through updates."""
    module = pytest.importorskip('weecfg.extension_manager', reason='needs repository support')
    config = station(tmp_path, html_root='weather-pages')
    first = make_release(tmp_path, '0.2.0')
    second = make_release(tmp_path, '0.2.1')
    releases = [first]
    document = {
        'schema_version': 1,
        'repository': {'id': 'test.livedata', 'name': 'LiveData test'},
        'packages': [{'id': 'livedata', 'installer_name': 'livedata', 'name': 'LiveData',
                      'description': 'Live readings through PHP', 'types': ['service', 'generator'],
                      'releases': releases}],
    }
    index = tmp_path / 'repository.json'
    index.write_text(json.dumps(document))
    manager = module.ExtensionManager(config)
    with manager.operation():
        manager.registry.add('livedata', str(index))
    manager.reload()
    manager.install('livedata', yes=True)
    secret = manager.config['StdRESTful']['LiveData']['secret']
    StdReportEngine(manager.config, None).run()

    releases.append(second)
    index.write_text(json.dumps(document))
    manager.updates(['livedata'], yes=True)
    StdReportEngine(manager.config, None).run()

    assert manager.store.read('livedata')['version'] == '0.2.1'
    assert manager.config['StdRESTful']['LiveData']['secret'] == secret
    endpoint = pathlib.Path(manager.config['WEEWX_ROOT']) / 'weather-pages' / 'live.php'
    assert "$SECRET   = '%s';" % secret in endpoint.read_text(encoding='utf-8')
    template = pathlib.Path(manager.config['WEEWX_ROOT']) / 'skins' / 'LiveData' / 'live.php'
    assert "$SECRET   = 'replace_me';" in template.read_text(encoding='utf-8')
