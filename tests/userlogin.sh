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

projects=$($curler GET https://iam.eu-de.otc.t-systems.com/v3/auth/projects \
	    | jq .projects)

$curler GET https://tms.eu-de.otc.t-systems.com/v1.0/predefine_tags \
     | jq '.tags[] | .key + "=" + .value'

$curler GET https://iam.eu-de.otc.t-systems.com/v3/users \
    | jq '.users[]| { id: .id, name: .name, description: .description }'

$curler GET https://iam.eu-de.otc.t-systems.com/v3/regions \
    | jq '.regions[] | .id '

project_id=$(echo "$projects" | jq -r '.[0].id')
project_name=$(echo "$projects" | jq -r '.[0].name')
project_region=$(echo "$project_name" | cut -d_ -f1)
echo "$project_region"

eval $(
  $curler login \
	--token "$OS_AUTH_TOKEN" \
	--project "$project_name" \
	--f shell
  $curler logout --token "$OS_AUTH_TOKEN"
)
$curler GET \
    https://ecs.$project_region.otc.t-systems.com/v2/$project_id/servers \
    | jq .


#~ OS_ECS_URL=https://ecs.eu-de.otc.t-systems.com

#~ bearer_token() {
  #~ echo "$1"
#~ }
#~ project_id() {
  #~ echo "$3"
#~ }


#~ stoken=$($curler login \
	#~ --project "$OS_SCOPED_PROJECT" \
	#~ --token "$(bearer_token $utoken)" \
	#~ --shell
	#~ )
#~ ( eval "$stoken" ; $curler GET \
	#~ "$OS_ECS_URL/v2/${OS_AUTH_PROJECT_ID}/servers" \
	#~ | jq '.servers[] | {name: .name, id: .id}')

#~ $curler -v logout  "$(bearer_token $utoken)"
#~ $curler -v logout "$(eval "$stoken" ; echo $OS_AUTH_TOKEN)"

#~ $curler GET \
  #~ --token $(bearer_token $utoken) \
  #~ "$OS_ECS_URL/v2/$(project_id $utoken)/servers" \
  #~ | jq .

#~ echo "$stoken"


