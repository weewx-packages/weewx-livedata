## Overview

This page describes the request sent by the WeeWX service and the checks in
`live.php`. For installation, see the
[README](../README.md#installation).

## The request

The service sends an HTTP `POST` with `Content-Type: application/json`, the
[live payload](how-it-works.md#the-live-file) as the body, and two headers:

```
X-Timestamp: 1788164045
X-Signature: 6f3c1b...
```

`X-Timestamp` is the Unix time when the request is signed, written as a decimal
string. It is separate from the observation timestamp in the JSON body.

The signature is the lowercase hexadecimal HMAC-SHA256 of the timestamp string
followed immediately by the raw body bytes, using the shared secret. In PHP:

``` php
hash_hmac('sha256', $stamp . $body, $SECRET)
```

The installer generates the secret in `weewx.conf`. The LiveData report
generates `live.php` using that saved secret. The request carries the
signature, not the secret.

## Receiver checks

`live.php` performs these checks in order:

1. The method must be `POST`. Other methods receive `405 POST only`.
2. The body must be readable and no larger than 65,536 bytes. A failed read or
   oversized body receives `413 Too large`.
3. `X-Timestamp` must contain only decimal digits and be within 120 seconds of
   the host's clock, in either direction. Otherwise the response is
   `401 Stale or missing timestamp`.
4. `X-Signature` must match the computed signature. The endpoint uses
   `hash_equals` for a constant-time comparison. A missing or wrong signature
   receives `401 Bad signature`.
5. The body must decode as JSON to a value other than `null`. Otherwise the
   response is `400 Not JSON`.

A refused request leaves the existing `live.json` untouched. The timestamp
check limits how long a captured signed request can be replayed. Use HTTPS for
the connection.

## Writing the file

The target is `live.json` in the directory holding `live.php`. PHP needs write
access to that directory.

The endpoint writes the unchanged request body to a temporary file in the same
directory, then renames it to `live.json`. The temporary name includes the PHP
process ID. Renaming within the same filesystem is atomic, so a reader sees a
complete old or new file during an update.

A successful write receives `204 No Content`. A failed write or rename
receives `500 Cannot write`, and the endpoint attempts to remove the temporary
file.

## Rotating the secret

Change the secret in `weewx.conf`, then restart WeeWX. The next LiveData
report run generates `live.php` with that secret; publish the generated
file to the web host. Keep the installed template unconfigured so future
report runs can regenerate it. Requests signed with a different secret
are refused until the hosted endpoint has the matching key.
