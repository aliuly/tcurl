#!/bin/sh
#
set -euf ; (set -o pipefail 2>/dev/null) && set -o pipefail || :

curler='python curler.py -v'
. ./aksk.env

$curler GET --domain https://tms.eu-de.otc.t-systems.com/v1.0/predefine_tags \
     | jq '.tags[] | .key + "=" + .value'

project_name=$(
  $curler GET https://iam.eu-de.otc.t-systems.com/v3/auth/projects \
    | jq -r '.projects[0].name'
)
project_id=$(
  $curler GET https://iam.eu-de.otc.t-systems.com/v3/auth/projects \
    | jq -r '.projects[0].id'
)
project_region=$(echo "$project_name" | cut -d_ -f1)

$curler GET \
    --project-name "$project_name" \
    https://ecs.$project_region.otc.t-systems.com/v2/$project_id/servers \
    | jq .

$curler GET https://iam.eu-de.otc.t-systems.com/v3/auth/projects \
    | jq '.projects[] | {id: .id, name: .name, description: .description }'


$curler GET --domain https://iam.eu-de.otc.t-systems.com/v3/users \
    | jq '.users[]| { id: .id, name: .name, description: .description }'

$curler GET https://iam.eu-de.otc.t-systems.com/v3/regions \
    | jq '.regions[] | .id '


#~ user_id=$(
  #~ $curler GET "$OS_AUTH_URL/v3.0/OS-CREDENTIAL/credentials/$OS_ACCESS_KEY" \
    #~ | jq -r .credential.user_id
  #~ )
#~ echo user_id=$user_id
#~ domain_id=$(
  #~ $curler GET $OS_AUTH_URL/v3/users/$user_id | jq -r .user.domain_id
#~ )
#~ $curler GET \
  #~ --domain-id "$domain_id" \
  #~ "$OS_TMS_URL/v1.0/predefine_tags" \
  #~

#~ projects=$($curler GET "$OS_AUTH_URL/v3/auth/projects")
#~ project_id=$(
    #~ echo "$projects" \
    #~ | jq -r '.projects[] | select(.name == "'"$OS_SCOPED_PROJECT"'") .id'
  #~ )
#~ $curler GET \
  #~ --project-id "$project_id" \
  #~ "$OS_ECS_URL/v2/${project_id}/servers" \
  #~ | jq '.servers[] | {name: .name, id: .id}'


