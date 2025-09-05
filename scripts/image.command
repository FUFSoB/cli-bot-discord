#!/bin/argparse --store
! image
@ Return image of an object.
% %(prog)s [options*] [query]
; query | type try_id | help query or id to get actual object
; -d --directory | help direct way to an object
; -n --number | type int | help number of result if object was searched
              | default 0
; -H --webhook | action store_true
               | help send as webhook (useful for inaccessible emojis)
; -u --url | action store_true | help just send url
|||

params return_on_error
previous_directory=$(pwd)
kind=`[ return from 'type(query)' ]`

if [ directory ]; then
    cd "$directory"

elif [ kind in ["object", "null", "id", "unicode_emoji", "color"] ]; then
    if [ query == "guild" ]; then
        cd /current/guild
    elif [ query == "status" ]; then
        cd /current/user/activities/%inside=.image_url%return
    elif [ not query ]; then
        cd /current/user
    else
        cd /get/"$query"
    fi

else
    cd /find/"$query"/%name=^[^\.]%range=${number}%return

fi

title=$(< .str)
image=$(< .image_url)
footer="$(pwd) [$(< .type)]"

cd $previous_directory

if [ url ]; then
    storage image | send

else
    if [ webhook ]; then args="-Hm client"; fi

    embed --title "$title" \
        --image "$image" \
        --footer "$footer" \
    | send $args

fi
