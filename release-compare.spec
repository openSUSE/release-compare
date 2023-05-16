#
# spec file for package release-compare
#
# Copyright (c) 2023 SUSE LLC
#
# All modifications and additions to the file contributed by third parties
# remain the property of their copyright owners, unless otherwise agreed
# upon. The license for this file, and modifications and additions to the
# file, is the same license as for the pristine package itself (unless the
# license for the pristine package is not an Open Source License, in which
# case the license is the MIT License). An "Open Source License" is a
# license that conforms to the Open Source Definition (Version 1.9)
# published by the Open Source Initiative.

# Please submit bugfixes or comments via https://bugs.opensuse.org/
#

%{?!python_module:%define python_module() python3-%{**}}
%define skip_python2 1
Name:           release-compare
Summary:        Release Compare Script
License:        GPL-3.0-or-later
Group:          Development/Tools/Building
URL:            https://github.com/openSUSE/release-compare
Version:        0.9.0
Release:        0
Source:         %name-%version.tar.xz
BuildArch:      noarch
Requires:       python3-PyYAML
BuildRequires:  %{python_module setuptools}
BuildRequires:  %{python_module pytest}
BuildRequires:  %{python_module PyYAML}
BuildRequires:  fdupes
BuildRequires:  python-rpm-macros
Requires:       python3-release-compare

%python_subpackages

%description
This package contains scripts to create changelog files relative
to last released result.

Note: you need to use a releasetarget definition in your OBS repository
      to get this working. And the release target needs to have published binaries.

%prep
%setup -q

%build
%python_build

%install
%python_install
%python_expand %fdupes %{buildroot}%{$python_sitelib}
mkdir -p $RPM_BUILD_ROOT/usr/lib/build/obsgendiff.d $RPM_BUILD_ROOT/%_defaultdocdir/%name
install -m 0755 create_changelog $RPM_BUILD_ROOT/usr/lib/build/obsgendiff.d/create_changelog

%check
%pytest

%files -n release-compare
%license LICENSE
%doc README.rst
/usr/lib/build

%files %{python_files}
%{python_sitelib}/release_compare
%{python_sitelib}/release_compare-%{version}*-info

%changelog
