# Publishing a release

The mutable `repository.json` index points to versioned GitHub release assets.
Publish the archive before adding it to the index. Keep old release assets and
hashes unchanged so stations can reproduce an installed version.

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
5. Append a release to `repository.json` with the version, archive URL, format,
   digest, compatible Python and WeeWX versions, and restart requirement.
   Validate it with `weectl extension repo validate repository.json`.
6. Commit and push the index. On a test station, refresh the source, search for
   `livedata`, install or update it, and run the `LiveData` report. Check that the
   generated endpoint accepts posts signed with the configured station key.

Repository IDs, package IDs and `installer_name` identify existing installations.
Keep them stable when adding releases. Keywords affect search and can change.
