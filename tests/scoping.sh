#!/bin/sh
#
# Test curler login/logout with username
#
set -euf ; (set -o pipefail 2>/dev/null) && set -o pipefail || :

curler='python curler.py -v'
. ./username.env

#
# Unscoped token
#
eval $($curler login \
	--user "$OS_USERNAME" \
	--passwd "$OS_PASSWORD" \
	--domain "$OS_USER_DOMAIN_NAME" \
	-f shell
      )
trap '$curler logout --token $OS_AUTH_TOKEN' EXIT

$curler GET \
    -H "X-Subject-Token:$OS_AUTH_TOKEN" \
    https://iam.eu-de.otc.t-systems.com/v3/auth/tokens \
    | jq .

projects=$($curler GET https://iam.eu-de.otc.t-systems.com/v3/auth/projects \
            | jq .projects)
project_name=$(echo "$projects" | jq -r '.[0].name')


eval $(
  $curler login \
	--token "$OS_AUTH_TOKEN" \
	--project "$project_name" \
	--f shell
  $curler logout --token "$OS_AUTH_TOKEN"
)
$curler GET \
    -H "X-Subject-Token:$OS_AUTH_TOKEN" \
    https://iam.eu-de.otc.t-systems.com/v3/auth/tokens \
    | jq .

