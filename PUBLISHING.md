# Publishing a release

The [shared package catalog](https://github.com/weewx-packages/catalog) lists
this extension. Publish the archive before adding its metadata to that catalog. Keep old release assets and hashes
unchanged so stations can reproduce an installed version.

1. Update `VERSION` in `install.py` and `bin/user/livedata.py`. Run the tests
   described in [README.md](README.md), including the PHP endpoint tests.
2. Commit the payload changes and tag that commit, for example `v0.2.0`.
3. Build the archive from the tag:

   ``` sh
   git archive --format=zip --prefix=weewx-livedata-0.2.0/ \
       --output=/tmp/weewx-livedata-0.2.0.zip v0.2.0 \
       install.py bin/user/livedata.py live.php skins LICENSE.txt README.md
   sha256sum /tmp/weewx-livedata-0.2.0.zip
   ```

4. Create the GitHub release for the tag and upload that ZIP. Download the
   published asset and compare its digest with the local archive.
5. Update the `livedata` entry in the shared catalog. Follow its
   [contribution guide](https://github.com/weewx-packages/catalog/blob/main/CONTRIBUTING.md)
   to supply the release metadata and validate the index.
6. On a test station running stock WeeWX, install the exact published URL:

   ```sh
   weectl extension install https://github.com/weewx-packages/weewx-livedata/releases/download/v0.2.0/weewx-livedata-0.2.0.zip --config /path/to/test-station/weewx.conf
   ```

   Substitute the version just published. Restart WeeWX yourself and run the
   `LiveData` report. Check that the generated endpoint accepts posts signed
   with the configured station key. Repository refresh and package-ID updates
   require the separate experimental package manager described in the README.

The catalog owns the repository identity. Keep the package ID and installer
name `livedata` stable when adding releases.
