from unittest.mock import patch, Mock
import filecmp
import os
import pathlib
import tempfile
import yaml
import json
import release_compare

new_changelog1 = """\
* Wed Mar 1 2023 somebody@somewhere.com
- some other changes CVE-2022-1234

* Tue Feb 28 2023 somebody@somewhere.com
- some more changes

* Mon Feb 27 2023 somebody@somewhere.com
- some changes
"""

new_changelog2 = """\
* Wed Mar 1 2023 somebody@somewhere.com
- some other changes

* Tue Feb 28 2023 somebody@somewhere.com
- some more changes

* Mon Feb 27 2023 somebody@somewhere.com
- some changes
"""

new_changelog3 = """\
* Wed Mar 1 2023 somebody@somewhere.com
- some other changes

* Tue Feb 28 2023 somebody@somewhere.com
- some more changes

* Mon Feb 27 2023 somebody@somewhere.com
- some changes
"""

new_anonym_changelog1 = """\
- some other changes CVE-2022-1234

- some more changes

- some changes
"""

old_changelog1 = """\
* Tue Feb 28 2023 somebody@somewhere.com
- some more changes

* Mon Feb 27 2023 somebody@somewhere.com
- some changes
"""

old_changelog2 = """\
* Mon Feb 27 2023 somebody@somewhere.com
- some changes
"""

img_history = {
  "1.0.11": [
    {
      "date": "2023-01-01T08:00:00",
      "change": "some image config change"
    }
  ]
}

new_changelog_dict = {
  'package1': new_changelog1.splitlines(),
  'package2': new_changelog2.splitlines(),
  'package3': new_changelog3.splitlines()
}

data_dir = os.path.join(str(pathlib.Path(__file__).parent), '../data')


def test_get_packages_from_file():
    pkgs = release_compare.get_packages_from_file(
        os.path.join(data_dir, 'input', 'KIWI', 'foo-os.x86_64-1.0.12-profile1-Build.report')
    )
    assert pkgs == ['package1', 'package2', 'package3']

    pkgs = release_compare.get_packages_from_file(
        os.path.join(data_dir, 'input', 'KIWI', 'foo-os.x86_64-1.0.12-profile1-Build.packages')
    )
    assert pkgs == ['package1', 'package2', 'package3']


@patch('release_compare.subprocess.Popen')
def test_write_pkg_info(mock_subprocess):
    release_compare.CONFIG = release_compare.Config('')
    with tempfile.TemporaryDirectory() as tmpdir:
        release_compare.ROOT = os.path.join(data_dir, 'input')
        os.mkdir(os.path.join(tmpdir, 'changelogs'))
        os.mkdir(os.path.join(tmpdir, 'rpms'))
        pkgs = release_compare.get_packages_from_file(
            os.path.join(data_dir, 'input', 'KIWI', 'foo-os.x86_64-1.0.12-profile1-Build.report')
        )
        release_compare.write_pkg_info(pkgs[0], tmpdir)
        with open(os.path.join(tmpdir, 'rpms', 'package1')) as inf:
            assert inf.read() == '1.2.3-1.2'


def test_parse_old_obsgendiff():
    release_compare.LOG = Mock()
    with tempfile.TemporaryDirectory() as tmpdir:
        pkgs, changelogs, history = release_compare.parse_old_obsgendiff(
            os.path.join(
                data_dir, 'input', 'KIWI',
                'foo-os.x86_64-1.0.12-profile1-Build.packages'
            ),
            tmpdir
        )
    assert 'package0' in pkgs
    assert 'package1' in pkgs
    assert 'package2' in pkgs
    assert changelogs['package1'] == old_changelog1.splitlines()
    assert history == img_history


def test_write_changelog():
    new_pkgs = release_compare.get_packages_from_file(
        os.path.join(data_dir, 'input', 'KIWI', 'foo-os.x86_64-1.0.12-profile1-Build.packages')
    )
    release_compare.CONFIG.anonymize_changes = False
    with tempfile.TemporaryDirectory() as tmpdir:
        old_pkgs, old_logs, old_history = release_compare.parse_old_obsgendiff(
            os.path.join(
                data_dir, 'input', 'KIWI',
                'foo-os.x86_64-1.0.12-profile1-Build.packages'
            ),
            tmpdir
        )

        changelog_data = release_compare.get_changelog_data(
            new_pkgs, new_changelog_dict, old_pkgs, old_logs
        )
        new_history_file = release_compare.match_changes_file(
            'foo-os.x86_64-1.0.12-profile1-Build',
            os.path.join(data_dir, 'input', 'SOURCES')
        )
        changelog_data['config-changes'] = release_compare.get_config_changes(
            new_history_file, old_history
        )

        release_compare.write_changelog_text(
            os.path.join(tmpdir, 'ChangeLog.txt'), changelog_data
        )
        release_compare.write_changelog_json(
            os.path.join(tmpdir, 'ChangeLog.json'), changelog_data
        )
        release_compare.write_changelog_yaml(
            os.path.join(tmpdir, 'ChangeLog.yaml'), changelog_data
        )

        assert open(os.path.join(tmpdir, 'ChangeLog.txt'), 'r').read() == open(os.path.join(data_dir, 'output', 'ChangeLog.txt'), 'r').read()
        assert filecmp.cmp(
            os.path.join(tmpdir, 'ChangeLog.txt'),
            os.path.join(data_dir, 'output', 'ChangeLog.txt')
        )
        # compare yaml and json content rather than verbatim
        # change in order is ok
        with open(os.path.join(tmpdir, 'ChangeLog.json'), 'r') as inf:
            generated_data = json.load(inf)
        with open(os.path.join(data_dir, 'output', 'ChangeLog.json'), 'r') as inf:
            expected_data = json.load(inf)
        assert generated_data == expected_data

        with open(os.path.join(tmpdir, 'ChangeLog.yaml'), 'r') as inf:
            generated_data = yaml.safe_load(inf)
        with open(os.path.join(data_dir, 'output', 'ChangeLog.yaml'), 'r') as inf:
            expected_data = yaml.safe_load(inf)
        assert generated_data == expected_data
