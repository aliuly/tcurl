#!/bin/sh
set -euf
(set -o pipefail >/dev/null 2>&1) && set -o pipefail || :
mydir=$(dirname "$(readlink -f "$0")")
venv="$mydir/.venv"
reqs=requirements.txt

if [ -d "$venv" ] ; then
  (
    [ x"$(cat "$venv/.realpath")" !=  x"$(readlink -f "$venv")" ] \
    || ! diff -U 0 --color "$venv/.$reqs" "$mydir/$reqs"
  ) && rm -rf "$venv"
fi
if [ ! -d "$venv" ] ; then
  if ! (
    python3 -m venv --system-site-packages "$venv"
    readlink -f "$venv" > "$venv/.realpath"
    cp "$mydir/$reqs" "$venv/.$reqs"
    . "$venv/bin/activate"
    pip install --requirement "$mydir/$reqs"
    pip install icecream
  ) ; then
    rm -rf "$venv"
    exit 1
  fi
fi
exit 0

