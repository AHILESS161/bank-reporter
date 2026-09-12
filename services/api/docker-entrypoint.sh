#!/bin/sh
set -eu

if find /usr/local/share/ca-certificates/local -type f \( -name '*.crt' -o -name '*.pem' \) -print -quit 2>/dev/null | grep -q .; then
  update-ca-certificates >/dev/null
fi

exec "$@"
