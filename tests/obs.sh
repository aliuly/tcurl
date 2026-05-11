#!/bin/sh
#
# Test curler login/logout with username
#
set -euf ; (set -o pipefail 2>/dev/null) && set -o pipefail || :

curler='python curler.py -v'
. ./username.env

eval $($curler login \
        --user "$OS_USERNAME" \
        --passwd "$OS_PASSWORD" \
        --domain "$OS_USER_DOMAIN_NAME" \
        -f shell
        )
trap '$curler logout $OS_AUTH_TOKEN' EXIT

$curler GET https://iam.eu-de.otc.t-systems.com/v3/regions \
    | jq '.regions[] | .id '

# Get a temp aksk
eval $($curler aksk --maxage 60 --format shell $OS_AUTH_TOKEN)
eval $($curler logout --shell $OS_AUTH_TOKEN)
trap '' EXIT

$curler GET \
    --awsv4-region eu-de \
    https://obs.eu-de.otc.t-systems.com





