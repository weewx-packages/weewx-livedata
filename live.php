<?php
#
#    Copyright (c) 2026 Manuel Hilgert
#
#    See the file LICENSE.txt for your rights.
#
# Receives the readings WeeWX posts and writes them to live.json beside this
# file. Pages read the JSON file without executing PHP.
#
# The station never sends the key. It sends a signature over the timestamp and
# the body, and this recomputes it. A post that was captured cannot be replayed
# once its timestamp has aged past MAX_AGE.

$SECRET   = 'replace_me';        # the installer writes this
$TARGET   = __DIR__ . '/live.json';
$MAX_AGE  = 120;                 # seconds a post stays acceptable
$MAX_SIZE = 65536;               # bytes; a payload is normally under 2 kB

function refuse($code, $why) {
    http_response_code($code);
    header('Content-Type: text/plain');
    exit($why . "\n");
}

if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
    refuse(405, 'POST only');
}

$body = file_get_contents('php://input', false, null, 0, $MAX_SIZE + 1);
if ($body === false || strlen($body) > $MAX_SIZE) {
    refuse(413, 'Too large');
}

$stamp = $_SERVER['HTTP_X_TIMESTAMP'] ?? '';
$given = $_SERVER['HTTP_X_SIGNATURE'] ?? '';
if (!ctype_digit($stamp) || abs(time() - (int)$stamp) > $MAX_AGE) {
    refuse(401, 'Stale or missing timestamp');
}

# hash_equals compares in constant time, so a wrong signature does not reveal
# how much of it was right.
if (!hash_equals(hash_hmac('sha256', $stamp . $body, $SECRET), $given)) {
    refuse(401, 'Bad signature');
}

if (json_decode($body) === null) {
    refuse(400, 'Not JSON');
}

# Written to a temporary file and renamed, because a browser may be reading the
# old one at this moment. The rename is atomic within one filesystem, so a reader
# gets either the whole old file or the whole new one, never half of either.
$tmp = $TARGET . '.' . getmypid() . '.tmp';
if (file_put_contents($tmp, $body) === false || !rename($tmp, $TARGET)) {
    @unlink($tmp);
    refuse(500, 'Cannot write');
}

http_response_code(204);
