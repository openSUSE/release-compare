#!/usr/bin/env python
# -*- encoding: utf-8 -*-

from os import path
from setuptools import setup
from setuptools.command import sdist as setuptools_sdist

import distutils
import subprocess

from release_compare.version import __version__

here = path.abspath(path.dirname(__file__))
with open(path.join(here, 'README.rst'), encoding='utf-8') as readme:
    long_description = readme.read()

config = {
    'name': 'release-compare',
    'long_description': long_description,
    'long_description_content_type': 'text/x-rst',
    'description': 'Release Compare - Image Changelog Tool',
    'author': 'Public Cloud Team',
    'url': 'https://github.com/openSUSE/release-compare',
    'download_url':
        'https://download.opensuse.org',
    'author_email': 'public-cloud-dev@susecloud.net',
    'version': __version__,
    'license' : 'GPLv3+',
    'install_requires': [
        'docopt',
        'PyYAML'
    ],
    'packages': ['release_compare'],
    'include_package_data': True,
    'zip_safe': False,
    'classifiers': [
       # classifier: http://pypi.python.org/pypi?%3Aaction=list_classifiers
       'Development Status :: 2 - Alpha',
       'Intended Audience :: Developers',
       'License :: OSI Approved :: '
       'GNU General Public License v3 or later (GPLv3+)',
       'Operating System :: POSIX :: Linux',
       'Programming Language :: Python :: 3.6',
       'Programming Language :: Python :: 3.8',
       'Programming Language :: Python :: 3.10',
       'Topic :: System :: Operating System',
    ]
}

setup(**config)
