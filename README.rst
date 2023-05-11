Release Compare
===============

This project contains a script **create_changelog** that analyzes an Open
Build Service image build and generated change log information. It is intended
to be run automatically in Open Build Service via its `obsgendiff` build hook.

When run in an OBS image build environemnt, after the image build is
completed, **create_changelog** scans the build environment and produces an
archive containing a list of the packages that were used to create the image,
plus version information and change log of said packages. The archive has the
extensions ``.obsgendiff`` and is stored in the directory
``/.build.packages/OTHER`` in the build environment.

Additionally, in case an **obsgendiff** archive of a previous build is
available, **create_changelog** produces one or more change log files listing
the differences in between the two builds. OBS can inject **obsgendiff**
archives from previous builds into the build environment, if the build target
repository has a ``releasetarget`` defined with the trigger ``obsgendiff`` in
its project meta configuration. **create_changelog** expects old
**obsgendiff** archives in ``/.build.packages/SOURCES``.

Change Log output
-----------------

**create_changelog** supports three different types of change log format, plain
text, YAML, and JSON. The produced change log contains the following sections:

1. removed (YAML/JSON) / Removed rpms (text)

   List of packages that are in the old build but are absent in the current one.

2. added / Added rpms

   List of packages that are in the current build but are absent in the old one.

3. source-changes / Package Source Changes

   This section the added change log entries for every package that is
   included in both images. Since sub-packages of the same source package have
   identical change log, the respective source packages of the binary packages
   are used for this, to avoid duplication. The text format output is the
   source package name on its own line, followed by a unidiff of the changes
   (additions only). The YAML and JSON formats use the source package name as
   keys with the changes assigned to them as a multiline string.

4. references / References

   List of CVE references, obtained by scanning the change logs for CVE tags.

5. config-changes (YAML/JSON only)

   In case both the previous build and the current build contain a file with
   the image version history, **create_changelog** produces a section containing
   the image configuration changes. The expected input format of the version
   history file is a YAML or a JSON file with one or more entries like this:

   .. code:: yaml

     version_tag:
       - date: ISO date string
         change: One-line change description
         details: Optional multi-line string description
       ...
     ...

   The file name of the image version history file is expected to be of the
   following scheme: `[<PROFILE>.]changes.{json,yaml}`

   `<PROFILE>` corresponds to build profile in case the image description is
   multi-build.

6. package-list (YAML/JSON only, optional)

   List of all packages installed in image. Not actually a change log, but
   potentially useful information, especially for net-new images which
   naturally do not have a change log.

Configuration
-------------

The **create_changelog** script accepts an optional configuration file, which
needs to be named ``_release_compare`` and be added to the image source
package. The format is as follows:

::

  <config>
      <param name="output_text">true/false</param>
      <param name="output_yaml">true/false</param>
      <param name="output_json">true/false</param>
      <param name="package_list">always/never/new</param>
      <param name="anonymize_changes">true/false</param>
      <param name="debug">true/false</param>
  </config>

Most should be self-explanatory. Default output modes are ``text`` and
``json``.  Parameter `package_list` controls whether the full package list is
included in the change log. The default setting of ``new`` only adds the full
package list for net new images, i.e. no matching previous **obsgendiff** was
found for the image in question. `anonymize_changes` if true (the default) will
cause **create_changelog** to strip packager names and email addresses from the
generated change log.

Command line usage
------------------

**create_changelog** is intended to be run as an **obsgendiff** hook in the
Open Build Service, but it can be used manually. For this purpose, it accepts
a command line parameter ``--root``, which can be used to change the default
directory where **create_changelog** expects the package and source
information, what would be ``/.build.packages`` in a KIWI image build
environment.
