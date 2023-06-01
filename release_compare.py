#!/usr/bin/python3

# Copyright (c) 2023 SUSE Software Solutions
#
# This library is free software; you can redistribute it and/or
# modify it under the terms of the GNU Library General Public
# License as published by the Free Software Foundation; either
# version 2 of the License, or (at your option) any later version.
#
# This library  is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Library General Public License for more details.
#
# You should have received a copy of the GNU Library General Public
# License along with this library; see the file COPYING.LIB. If not,
# write to the Free Software Foundation, Inc., 59 Temple Place,
# Suite 330, Boston, MA  02111-1307, USA
import argparse
import difflib
import glob
import json
import logging
import os
import pathlib
import re
import shutil
import subprocess
import tempfile
import textwrap
import traceback
import yaml
import xml.etree.ElementTree as ET
from setuptools._vendor.packaging import version as pkg_version
from urllib.parse import urlparse

__version__ = '0.9.0'
__log_version__ = '2'

LOG = None
CONFIG = None
ROOT = None


class Config:
    def __init__(self, config_file):
        # defaults
        self.output_text = True
        self.output_yaml = False
        self.output_json = True
        self.package_list = 'new'
        self.anonymize_changes = True
        self.debug = False

        if os.path.exists(config_file):
            tree = ET.parse(config_file)
            root = tree.getroot()
            for elem in root.findall('./param'):
                param = elem.get('name')
                value = str(elem.text)
                if param == 'output_text':
                    self.output_text = value.lower() == 'true'
                elif param == 'output_json':
                    self.output_json = value.lower() == 'true'
                elif param == 'output_yaml':
                    self.output_yaml = value.lower() == 'true'
                elif param == 'package_list':
                    if value not in ['always', 'new', 'never']:
                        raise Exception(
                            'Unknown config value "{}" for parameter "package_list"'.format(value)
                        )
                    self.package_list = value
                elif param == 'anonymize_changes':
                    self.anonymize_changes = value.lower() == 'true'
                elif param == 'debug':
                    self.debug = value.lower() == 'true'
                else:
                    LOG.warning('Unknown config parameter "{}"'.format(param))


class PackageInfo:
    def __init__(self, name, version, release=None, arch=None, source=None, repo=None):
        self.name = name
        self.version = version
        self.release = release
        self.arch = arch
        self.source = source
        self.repo = repo

    def __eq__(self, s):
        return self.name == s

    def __repr__(self):
        return self.name

    def __str__(self):
        return self.name

    def get_src_name(self):
        # source URL format is obs://build.suse.de/SUSE:PROJECT:SUB/repo/hash-pkg_name[.maint_prj]
        # .maint_prj is only there when PROJECT is a maintenance project
        # since package names may contain dots, simply cutting off trailing '\..*' is not an option
        p = pathlib.Path(urlparse(self.source).path)
        is_maint = 'Maintenance' in p.parts[1]
        p_name = p.name[p.name.find('-')+1:]
        if is_maint:
            last_dot = p_name.rfind('.')
            if last_dot == -1:
                LOG.warn('expected maintenance suffix in "{}", continuing'.format(p.name))
            else:
                p_name = p_name[:last_dot]
        return p_name

    def get_path(self, pkg_root):
        filename_long = '{name}-{version}-{release}.{arch}.rpm'.format(
            name=self.name,
            version=self.version,
            release=self.release,
            arch=self.arch
        )
        filename_short = '{name}.rpm'.format(name=self.name)
        if not self.repo:
            # no reliable path info available, as the KIWI cache uses the release
            # project names not the maintenance names, and the release project
            # names only exist with : transformed to _ in the .packages file;
            # instead of guessing the real project name, we just scan the whole
            # tree for the package with the right name. There should be only
            # one anyway.
            pkg_path = next(pathlib.Path(pkg_root).rglob(filename_long), None)
            if not pkg_path:
                # appliance build in OBS uses short format
                pkg_path = next(pathlib.Path(pkg_root).rglob(filename_short), None)
            if pkg_path:
                pkg_path = str(pkg_path)
        else:
            pkg_path = os.path.join(pkg_root, self.repo, filename_long)
            if not os.path.exists(pkg_path):
                pkg_path = os.path.join(pkg_root, self.repo, filename_short)
            if not os.path.exists(pkg_path):
                pkg_path = None
        return pkg_path


def get_packages_from_report_file(report_file):
    tree = ET.parse(report_file)
    root = tree.getroot()
    pkgs = []

    for item in root.findall('./binary'):
        pkg_name = item.get('name')
        if pkg_name:
            pkgs.append(
                PackageInfo(
                    name=pkg_name,
                    version=item.get('version'),
                    release=item.get('release'),
                    arch=item.get('binaryarch'),
                    source=item.get('disturl'),
                    repo=os.path.join(item.get('project'), item.get('repository'))
                )
            )

    return pkgs


def get_packages_from_packages_file(packages_file):
    pkgs = []
    line_no = 0

    with open(packages_file, 'r') as ins:
        line = ins.readline()
        while line:
            records = line.split('|')
            line_no += 1
            try:
                if records[5] == '(none)' or records[5] == '':
                    LOG.debug('ignoring package "{}", no source information'.format(records[0]))
                else:
                    pkgs.append(
                        PackageInfo(
                            name=records[0],
                            version=records[2],
                            release=records[3],
                            arch=records[4],
                            source=records[5]
                        )
                    )
            except IndexError:
                LOG.warn('line no {} in {} does not have expected format, skipping'.format(
                    line_no, packages_file)
                )
            line = ins.readline()

    return pkgs


def get_packages_from_file(data_file):
    if data_file.endswith('.report'):
        return get_packages_from_report_file(data_file)
    elif data_file.endswith('.packages'):
        return get_packages_from_packages_file(data_file)
    else:
        raise RuntimeError('{}: unkown report file format'.format(data_file))


def write_pkg_info(pkg, outdir):
    rpm = pkg.get_path(os.path.join(ROOT, 'SOURCES', 'repos'))
    if not rpm or not os.path.exists(rpm):
        LOG.warning('could not find rpm for package "{}", skipping'.format(pkg.name))
    else:
        rpm_src_name = pkg.get_src_name()
        with open(os.path.join(outdir, 'changelogs', rpm_src_name), 'w', encoding='UTF-8') as outf:
            subprocess.Popen(
                [
                    'rpm', '-qp', rpm, '--changelog', '--nodigest', '--nosignature'
                ],
                env={'LC_ALL': 'C.UTF-8'},
                stdout=outf
            )
        with open(os.path.join(outdir, 'rpms', pkg.name), 'w') as outf:
            outf.write('{}-{}'.format(pkg.version, pkg.release))


def get_pkg_changelog(pkg):
    rpm = pkg.get_path(os.path.join(ROOT, 'SOURCES', 'repos'))
    if not rpm or not os.path.exists(rpm):
        LOG.warning('could not find rpm for package "{}", cannot read changelog'.format(pkg.name))
        return None
    else:
        proc = subprocess.Popen(
            [
                'rpm', '-qp', rpm, '--changelog', '--nodigest', '--nosignature'
            ],
            env={'LC_ALL': 'C.UTF-8'},
            stdout=subprocess.PIPE
        )
        return [x.decode('utf-8').rstrip('\n') for x in proc.stdout.readlines()]


def get_matching_files(search_dir, regex):
    match_re = re.compile(regex)
    files = os.listdir(search_dir)
    matches = []
    for f in files:
        if match_re.fullmatch(f):
            matches.append(f)
    return matches


def get_latest_obsgendiff_version(filenames):
    if len(filenames) == 1:
        return filenames[0]
    version_re = re.compile(r'(-)([0-9]+(\.[0-9]+)+)(-)')
    build_re = re.compile(r'(Build)([0-9]+(\.[0-9]+)?)')
    last_version = pkg_version.Version('0.0.0')
    last_build = pkg_version.Version('0.0')
    latest = None
    LOG.debug('finding latest obsgendiff')
    for f in filenames:
        LOG.debug('  considering {}'.format(f))
        cur_version = 0
        cur_build = 0
        version_match = version_re.search(f)
        build_match = build_re.search(f)
        if version_match:
            cur_version = pkg_version.parse(version_match.group(2))
        if build_match:
            cur_build = pkg_version.parse(build_match.group(2))
        if (
                (cur_version > last_version) or
                (cur_version == last_version and cur_build > last_build)
        ):
            latest = f
            last_version = cur_version
            last_build = cur_build
            LOG.debug('  new candidate {}'.format(f))
    return latest


def extract_old_obsgendiff(report_file, outdir):
    image_name_full = pathlib.Path(report_file).stem
    build_match = re.search(r'(Build)([0-9]+(\.[0-9]+)?)?', image_name_full)
    if build_match:
        obsgendiff_regex = r'{}Build[0-9]+(\.[0-9]+){}.obsgendiff'.format(
            re.escape(image_name_full[:build_match.start()]),
            re.escape(image_name_full[build_match.end():])
        )
    else:
        # no build number fallback (e.g. Jump ftp tree)
        LOG.debug('{} does not contain a build number'.format(report_file))
        if image_name_full.endswith('-Media1'):
            obsgendiff_regex = r'{}-Build[0-9]+(\.[0-9]+)-Media1.obsgendff'.format(
                re.escape(image_name_full[:-7])
            )
        else:
            LOG.warning(
                '{} no build number and not a Media report file, skipping'.format(report_file)
            )
            return None
    LOG.debug('using regex "{}" to select old obsgendiff'.format(obsgendiff_regex))
    src_matches = get_matching_files(os.path.join(ROOT, 'SOURCES'), obsgendiff_regex)
    if not src_matches:
        LOG.debug(
            'no old obsgendiff found for "{}", trying for older versions'.format(image_name_full)
        )
        # matching in a regex string, so we need to match escapes as well, hence
        # all the backslashes
        version_match = re.search(r'-[0-9]+(\\\.[0-9]+)+\\-', obsgendiff_regex)
        if version_match:
            obsgendiff_regex = r'{}-[0-9]+(\.[0-9]+)+-{}'.format(
                obsgendiff_regex[:version_match.start()],
                obsgendiff_regex[version_match.end():]
            )
            LOG.debug('using regex "{}" to select old obsgendiff'.format(obsgendiff_regex))
            src_matches = get_matching_files(os.path.join(ROOT, 'SOURCES'), obsgendiff_regex)
        else:
            LOG.warning('no version number found in "{}"'.format(image_name_full))
            return None
    obsgendiff = get_latest_obsgendiff_version(src_matches)
    if not obsgendiff:
        LOG.warning('no old obsgendiff found for "{}"'.format(image_name_full))
        return None
    extract_dir = os.path.join(outdir, 'obsgendiff.released')
    os.mkdir(extract_dir)
    LOG.info('extracting {}'.format(obsgendiff))
    subprocess.call(['tar', 'xf', os.path.join(ROOT, 'SOURCES', obsgendiff), '-C', extract_dir])
    return os.path.join(outdir, extract_dir)


def load_file(input_file, loader):
    try:
        with open(input_file, 'r') as inf:
            return loader(inf)
    except Exception as error:
        LOG.warning('error loading {} ({})'.format(input_file, str(error)))
        if CONFIG.debug:
            print(traceback.format_exc())
        return None


def parse_old_obsgendiff(report_file, tmpdir):
    extract_path = extract_old_obsgendiff(report_file, tmpdir)
    if not extract_path:
        return [], {}, None
    pkgs = []
    changelogs = {}
    rpms = os.listdir(os.path.join(extract_path, 'rpms'))

    for rpm in rpms:
        with open(os.path.join(extract_path, 'rpms', rpm), 'r') as in_file:
            fullver = in_file.read()
        pkgs.append(PackageInfo(rpm, *fullver.split('-')))

    changes_files = os.listdir(os.path.join(extract_path, 'changelogs'))
    for changes_file in changes_files:
        with open(os.path.join(extract_path, 'changelogs', changes_file),
                  'r', encoding='utf-8') as in_file:
            changelogs[changes_file] = [x.rstrip('\n') for x in in_file.readlines()]

    history = None
    history_file = os.path.join(extract_path, 'image_changes.json')
    loader = json.load
    if not os.path.exists(history_file):
        history_file = os.path.join(extract_path, 'image_changes.yaml')
        loader = yaml.safe_load
    if not os.path.exists(history_file):
        LOG.warning('No image version history in old obsgendiff')
    else:
        history = load_file(history_file, loader)
    return pkgs, changelogs, history


def compare_changelogs(changes_old, changes_current):
    if not changes_old or not changes_current:
        # unless there was a problem with package query or with
        # the old obsgendiff, this should not happen
        return 'n/a'
    differ = difflib.Differ()
    changes = ''
    delta = differ.compare(changes_old, changes_current)

    if CONFIG.anonymize_changes:
        email_re = re.compile(r'\+ \* .*@.*')
    else:
        email_re = None
    for line in delta:
        if line.startswith('+ '):
            if not email_re or not email_re.match(line):
                changes += line[2:] + '\n'
        else:
            # stop once we've reached the first line that is not an addition
            # existing change log entries are not supposed to be altered anyway
            break
    return changes.rstrip('\n')


def get_changelog_data(new_pkgs, new_changelogs, old_pkgs, old_changelogs):
    cl_dict = {
        'format-version': __log_version__,
        'removed': [],
        'added': [],
        'source-changes': {},
        'references': [],
        'config-changes': {}
    }

    for pkg in new_pkgs:
        if pkg not in old_pkgs:
            cl_dict['added'].append(pkg.name)

    for pkg in old_pkgs:
        if pkg not in new_pkgs:
            cl_dict['removed'].append(pkg.name)

    common_logs = []
    for changelog in new_changelogs:
        if changelog in old_changelogs:
            common_logs.append(changelog)

    # diff package changelogs and generate list of CVEs
    cve_refs = set()
    cve_re = re.compile(r'CVE-[0-9]{4}-[0-9]+')
    for clog in common_logs:
        changes = compare_changelogs(old_changelogs[clog], new_changelogs[clog])
        if changes:
            cl_dict['source-changes'][clog] = changes
            cve_matches = cve_re.findall(changes)
            for cve_match in cve_matches:
                cve_refs.add(cve_match)
    cl_dict['references'] = sorted(cve_refs)
    return cl_dict


def write_changelog_text(output_file, changelog):
    with open(output_file, 'w', encoding='utf-8') as outf:
        outf.write('Removed rpms\n')
        outf.write('============\n')
        if changelog.get('removed'):
            outf.write('\n - ')
            print(*changelog['removed'], sep='\n - ', file=outf)
        outf.write('\nAdded rpms\n')
        outf.write('==========\n')
        if changelog.get('added'):
            outf.write('\n - ')
            print(*changelog['added'], sep='\n - ', file=outf)
        outf.write('\nPackage Source Changes\n')
        outf.write('======================\n')
        if changelog.get('source-changes'):
            outf.write('\n')
            for src_name, changes in changelog['source-changes'].items():
                print(src_name, file=outf)
                outf.write(textwrap.indent(changes, '+ ', lambda line: True))
                outf.write('\n')
        outf.write('\nReferences\n')
        outf.write('==========\n')
        if changelog.get('references'):
            outf.write('\n - ')
            print(*changelog['references'], sep='\n - ', file=outf)


def write_changelog_yaml(output_file, changelog):
    with open(output_file, 'w') as outf:
        yaml.dump(changelog, outf, default_flow_style=False, sort_keys=False)


def write_changelog_json(output_file, changelog):
    with open(output_file, 'w') as outf:
        json.dump(changelog, outf, indent=2, sort_keys=False)


def match_changes_file(image_name, sources_dir):
    changes_files = glob.glob(os.path.join(sources_dir, '*changes.json'))
    if not changes_files:
        changes_files = glob.glob(os.path.join(sources_dir, '*changes.yaml'))
    if not changes_files:
        LOG.warning('No version history file in {}'.format(sources_dir))
        return None
    if len(changes_files) == 1:
        return changes_files[0]
    else:
        # figure out right changes files
        for changes_file in changes_files:
            profile_name = pathlib.Path(changes_file).name.split('.')[0]
            if '-'+profile_name+'-' in image_name:
                return changes_file
        else:
            LOG.warning('No changes file in {} matches {}'.format(sources_dir, image_name))
            return None


def get_config_changes(new_history_file, old_history):
    if new_history_file.endswith('.json'):
        loader = json.load
    elif new_history_file.endswith('.yaml'):
        loader = yaml.safe_load
    else:
        LOG.warning('unknown format "{}", cannot parse image history')
        return {}

    LOG.debug('using image version history from {}'.format(new_history_file))
    history = load_file(new_history_file, loader)
    config_changes = {}
    for ver in history:
        if ver not in old_history:
            config_changes[ver] = history[ver]
    return config_changes


def create_changelog(root) -> None:
    global ROOT
    global CONFIG
    global LOG
    ROOT = root
    CONFIG = Config(os.path.join(ROOT, 'SOURCES', '_release_compare'))
    if CONFIG.debug:
        log_level = logging.DEBUG
    else:
        log_level = logging.INFO
    logging.basicConfig(level=log_level, format='%(name)s:[%(levelname)s] %(message)s')
    LOG = logging.getLogger('create_changelog')

    report_files = glob.glob(os.path.join(ROOT, 'OTHER', '*.report'))
    report_files += glob.glob(os.path.join(ROOT, 'KIWI', '*.packages'))
    report_files += glob.glob(os.path.join(ROOT, 'DOCKER', '*.packages'))

    os.makedirs(os.path.join(ROOT, 'OTHER'), exist_ok=True)

    for report in report_files:
        if '-Media2' in report or '-Media3' in report:
            # skip source and debug media
            continue

        LOG.info('parsing {}'.format(report))
        pkgs = get_packages_from_file(report)
        pkg_changelogs = {}
        image_name = pathlib.Path(report).stem

        for pkg in pkgs:
            # RPM change logs are identical for all sub packages
            # so we store and diff them based on source packages names
            src_name = pkg.get_src_name()
            if not pkg_changelogs.get(src_name):
                pkg_changelogs[src_name] = get_pkg_changelog(pkg)

        history_file = match_changes_file(image_name, os.path.join(ROOT, 'SOURCES'))
        image_net_new = False

        with tempfile.TemporaryDirectory() as tmpdir:
            LOG.info('writing package version info and change logs')
            os.mkdir(os.path.join(tmpdir, 'changelogs'))
            os.mkdir(os.path.join(tmpdir, 'rpms'))

            for pkg in pkgs:
                write_pkg_info(pkg, tmpdir)

            if history_file:
                shutil.copyfile(
                    history_file,
                    os.path.join(tmpdir, './image_changes' + pathlib.Path(history_file).suffix)
                )
            else:
                LOG.warning('image "{}" does not have a changes file'.format(image_name))

            obsgendiff = os.path.join(ROOT, 'OTHER', image_name + '.obsgendiff')
            LOG.info('creating obsgendiff {}'.format(obsgendiff))
            subprocess.call(['tar', 'cfJ', obsgendiff, '-C', tmpdir, '.'])

            (
                released_pkgs,
                released_changelogs,
                released_history
            ) = parse_old_obsgendiff(report, tmpdir)
            changelog_name = 'ChangeLog.' + image_name
            changelog_data = {}

            if released_pkgs:
                LOG.info('collecting change information')
                changelog_data = get_changelog_data(
                    pkgs,
                    pkg_changelogs,
                    released_pkgs,
                    released_changelogs
                )
            else:
                LOG.warning(
                    'no information about released packages available, treating as net new release'
                )
                image_net_new = True

            if (CONFIG.package_list == 'yes' or (image_net_new and CONFIG.package_list == 'new')):
                changelog_data['package-list'] = [
                    {'name': x.name, 'version': x.version} for x in pkgs
                ]

            if released_history and history_file:
                config_changes = get_config_changes(
                    history_file,
                    released_history
                )
                changelog_data['config-changes'] = config_changes
            else:
                LOG.warning(
                    'no information about released image history, not generating config changelog'
                )

            if CONFIG.output_text:
                LOG.info('writing {}'.format(changelog_name + '.txt'))
                write_changelog_text(
                    os.path.join(ROOT, 'OTHER', changelog_name + '.txt'),
                    changelog_data
                )
            if CONFIG.output_yaml:
                LOG.info('writing {}'.format(changelog_name + '.yaml'))
                write_changelog_yaml(
                    os.path.join(ROOT, 'OTHER', changelog_name + '.yaml'),
                    changelog_data
                )
            if CONFIG.output_json:
                LOG.info('writing {}'.format(changelog_name + '.json'))
                write_changelog_json(
                    os.path.join(ROOT, 'OTHER', changelog_name + '.json'),
                    changelog_data
                )


def main():
    parser = argparse.ArgumentParser(
        prog='create_changelog',
        description='Generate change log data from image build'
    )
    parser.add_argument('--version', action='version', version=__version__)
    parser.add_argument(
        '--root',
        default='/.build.packages',
        help="Root directory of packages build info [default: /.build.packages]"
    )
    args = parser.parse_args()
    create_changelog(args.root)


if __name__ == '__main__':
    main()
