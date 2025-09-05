#!/bin/argparse --store
! info
@ Return information about an object.
% %(prog)s [options*] [query]
; query | nargs * | type try_id | help query or id to get actual object
; -d --directory | help direct way to an object
; -H --webhook | action store_true
               | help send as webhook (useful for inaccessible emojis)
|||

params return_on_error
previous_directory=$(pwd)
if [ directory ]; then
    cd "$directory"

else
    cd /
    first=true
    for point in $(storage query); do
        kind=`[ return from 'type(point)' ]`
        if [ point in ["image"] ]; then
            $point -d `pwd` | return
        elif [ kind == "object" ]; then
            if $first; then
                cd $({
                    mapping guild=current/guild \
                        channel=current/channel \
                        message=current/message \
                        author=current/user \
                        category=current/channel/category \
                        roles=current/user/roles \
                        status=current/user/activity \
                        activity=current/user/activity \
                        activities=current/user/activities \
                        permissions=current/user/permissions \
                        spotify=current/user/activities/spotify \
                        game=current/user/activities/game \
                        rpc=current/user/activities/activity \
                        stream=current/user/activities/streaming
                    pointer $point
                } | get -f)
            else
                cd $({
                    mapping status=activity \
                        spotify=activities/spotify \
                        game=activities/game \
                        stream=activities/streaming
                    pointer $point
                } | get -f)
            fi
        elif [ kind in ["id", "unicode_emoji", "color"] ]; then
            cd get/$point
        elif [ kind in ["user", "channel", "role", "emoji"] ]; then
            cd get/$(dism -R $point)
        elif [ kind == "int" and file\(".count"\) ]; then
            cd %name=^[^\.]%range=$point%return
        elif [ kind == "null" ]; then
            if $first; then cd current/user; fi
        else
            cd find/"$point"
            if [ file\(".count", "content"\) == 1 ]; then
                cd %return
            fi
        fi
        first=false
    done
    if $first; then cd current/user; fi

fi

try cd .cache
kind=$(try cat .type <<< unknown)
title=$(try cat .str <<< $type)
description=""
thumbnail=$(try cat .image_url)
footer="$(pwd) [$kind]"
color=ffffff

function default {
    desc="\\n__ID__: **$(< id)**\\n"
    desc+="__Created at__: **$(date < created_at)**\\n"
    desc+="**•** *$(datedelta < created_at) elapsed*"
    if [ _args[-1] == "guild" and file\("guild"\) ]; then
        desc+="\\n__Guild__: **$(< guild/name)**\\n"
        desc+="**•** ID: **$(< guild/id)**"
    fi
    return "$desc"
}

if [ kind == "list" ]; then
    list=$(ls)
    echo -e "$list\\n$(pwd)"
    cd $previous_directory
    return

elif [ kind in ["user", "member", "webhook"] ]; then
    title=$(< display_name)
    description+="__Discord tag__: **$(< .str)**"
    if ./bot; then description+=" (bot)"; fi
    if [ \
        kind == "member" \
        and file\("id", "content"\) == file\("guild/owner/id", "content"\) \
    ]; then
        description+=" (owner)"
    fi
    description+=`default`
    if [ kind == "member" ]; then
        description+="\\n__Joined at__: **$(date < joined_at)**\\n"
        description+="**•** *$(datedelta < joined_at) elapsed*\\n"
        description+="__Status__: **$({
            mapping online=online \
                offline=offline \
                idle=idle \
                dnd=dnd
            pointer $(< status)
        } | get)**"
        if ./is_on_mobile; then description+=" (mobile)"; fi
        if [ file\("activity"\) ]; then
            activity_type=$(< activity/.type)
            description+="\\n**•** __$({
                mapping customactivity="Custom activity" \
                    game=Playing \
                    streaming=Streaming \
                    activity=Activity \
                    spotify=Spotify
                pointer $activity_type
            } | get)__"
            if [ activity_type == "customactivity" ]; then
                if [ file\("activity/emoji"\) ]; then
                    description+=": $(< activity/emoji/.discord)"
                else
                    description+=": "
                fi
                if [ file\("activity/name"\) ]; then
                    description+=" **$(< activity/name)**"
                fi
            else
                description+=": **$(< activity/.str)**"
            fi
        fi
        if [ file\("premium_since"\) ]; then
            description+="\\n__Boosting since__: **$(date < premium_since)**"
            description+="\\n**•** *$(datedelta < premium_since) elapsed*"
        fi
        description+="\\n__Color__: **$(< color)**"
        if [ file\("roles/.count", "content"\) > 1 ]; then
            filter=%name=^[^\\.]%range=:0:-1%relative=^roles%relative=
            if [ file\("guild/id", "content"\) == _guild ]; then
                ls -NE roles/${filter}mention | split | storage roles
            else
                ls -NE roles/${filter}name | split | storage roles
            fi
            description+="\\n__Roles__: $(storage roles | cat -PL | join ', ')"
        fi
        color=`[ return from 'file("color", "content")[1:]' ]`
    fi

elif [ kind == "guild" ]; then
    description+=`default`
    if [ file\("owner"\) ]; then
        description+="\\n__Owner__: **$(< owner/.str)**"
        if owner/bot; then description+=" (bot)"; fi
        description+="\\n**•** ID: **$(< owner_id)**\\n"
    else
        description+="\\n__Owner ID__: **$(< owner_id)**\\n"
    fi
    description+="__Region__: **$(< region)**\\n"
    description+="__Verification__: **$(< verification_level)**\\n"
    description+="**•** __MFA__: **$(< mfa_level)**; "
    description+="__Explicit filter__: **$(< explicit_content_filter)**\\n"
    description+="__Nitro boosts__: **$(< premium_subscription_count)** "
    description+="*(level: $(< premium_tier))*\\n"
    cd members/.cache
    description+="__Total members__: **$(< .count)** "
    description+="*(online: $(< .online_count))*\\n"
    description+="**•** **$(< .user_count)/$(< .bot_count)** "
    description+="*(users/bots)*\\n"
    cd ../channels/.cache
    description+="__Total channels__: **$(< .count)**\\n"
    description+="**•** __Category__: "
    description+="**$(try cat .category/.count <<< 0)**\\n"
    description+="**•** __Text__: "
    description+="**$(try cat .text/.count <<< 0)**\\n"
    description+="**•** __Voice__: "
    description+="**$(try cat .voice/.count <<< 0)**\\n"
    cd ..
    description+="__Total roles__: **$(< roles/.count)**\\n"
    description+="__Total emojis__: **$(< emojis/.count)**"

elif [ kind == "emoji" ]; then
    description+=`default guild`

elif [ kind == "partialemoji" ]; then
    description+="__Representation__: **\\$(unicode demojize $(< .str))**\\n"
    description+="__Unicode__: **U+$(unicode hex $(< .str))**\\n"
    description+="||Why do you even need info about default emoji?||"

elif [ kind in ["textchannel", "voicechannel", "categorychannel"] ]; then
    description+=`default guild`
    description+="\\n__Type__: **$(< type)**"
    if [ file\("category"\) ]; then
        description+="\\n__Category__: **$(< category/name)**\\n"
        description+="**•** ID: **$(< category/id)**"
    fi
    if [ kind == textchannel ]; then
        description+="\\n__Slowmode__: **$(< slowmode_delay)**\\n"
        description+="__NSFW__: **$(< nsfw)**\\n"
        description+="__Topic__: **$(< topic)**"
    elif [ kind == voicechannel ]; then
        description+="\\n__Bitrate__: **$(replace 000 ' kbps' < bitrate)**\\n"
        description+="__User limit__: **$(< user_limit)**"
    else
        filter=%name=^[^\\.]%relative=^channels%relative=mention
        ls -NE channels/${filter} | split | storage inner
        description+="\\n__Channels__: $(storage inner | cat -PL | join ', ')"
    fi

elif [ kind == "role" ]; then
    description+=`default guild`
    description+="\\n__Position__: **$(< position)**\\n"
    description+="__Hoist__: **$(< hoist)**\\n"
    description+="__Mentionable__: **$(< mentionable)**\\n"
    description+="__Color__: **$(< color)**\\n"
    filter=%name=^[^\\.]%relative=^members%relative=mention
    ls -NE members/${filter} | split | storage inner
    description+="__Members__: $(storage inner | cat -PL | join ', ')"
    color=`[ return from 'file("color", "content")[1:]' ]`

elif [ kind == "message" ]; then
    description+=`default guild`
    description+="\\n__Channel__: **$(< channel/.str)**\\n"
    description+="**•** ID: **$(< channel/id)**\\n"
    description+="__Author__: **$(< author/.str)**\\n"
    description+="**•** ID: **$(< author/id)**"
    url=$(< jump_url)

elif [ kind in ["customactivity", "game", "streaming", "spotify", "activity"] ]; then
    if [ from 'contains("/activities/", pwd())' ]; then
        prev=../..
    else
        prev=..
    fi
    author="$(< $prev/.str) (status)"
    author_icon=$(< $prev/.image_url)
    description+="__Status__: **$({
        mapping online=online \
            offline=offline \
            idle=idle \
            dnd=dnd
        pointer $(< $prev/status)
    } | get)**"
    if $prev/is_on_mobile; then description+=" (mobile)"; fi
    description+="\\n__Type__: **$(< .type)**\\n"
    if [ kind == "spotify" ]; then
        url="https://open.spotify.com/track/$(< track_id)"
        color=`[ return from 'file("color", "content")[1:]' ]`
        description+="__Title__: **$(< title)**\\n"
        description+="__Album__: **$(< album)**\\n"
        description+="__Artist__: **$(< artist)**\\n"
        description+="__Duration__: **$(date '%H:%M:%S' < duration)**\\n"
        description+="**•** *$(datedelta -r '%h:%M:%S' < end) left*"
    elif [ kind == "game" ]; then
        pass
    elif [ kind == "streaming" ]; then
        url=$(< url)
        description+="__Title__: **$(< name)**\\n"
        description+="__Game__: **$(< game)**\\n"
        description+="__Platform__: **$(< platform)**"
    elif [ kind == "customactivity" ]; then
        title="Custom Activity"
        description+="__Emoji__: **$(< emoji/.discord)**\\n"
        description+="__Text__: **$(< name)**"
    else
        description+="__State__: **$(< state)**\\n"
        description+="__Details__: **$(< details)**"
        if [ file\("large_image_url"\) ]; then
            description+="\\n__Large image__: "
            if [ file\("large_image_text"\) ]; then
                description+="**[$(< large_image_text)]($(< large_image_url))**"
            else
                description+="*[open image]($(< large_image_url))*"
            fi
        fi
        if [ file\("small_image_url"\) ]; then
            description+="\\n__Small image__: "
            if [ file\("small_image_text"\) ]; then
                description+="**[$(< small_image_text)]($(< small_image_url))**"
                footer_icon=$(< small_image_url)
            else
                description+="*[open image]($(< small_image_url))*"
            fi
        fi
    fi

elif [ kind in ["permissions", "permissionoverwrite"] ]; then
    author="$(< ../.str)"
    author_icon=$(< ../.image_url)
    title="Permissions"
    description+='\`\`\`m\\n'
    for perm in $({ ls | split -e '\s+'; segment :-1; } | get); do
        description+=`[ return \
            f"{perm:>21}  " + file\(perm, "content"\) + "\n" \
        ]`
    done
    description+='\`\`\`'

else
    description+=`default`

fi

if [ webhook ]; then args="-Hm client"; fi

embed --title "$title" \
      --description "$description" \
      --color $color \
      --url "$url" \
      --thumbnail "$thumbnail" \
      --author "$author" \
      --author-icon "$author_icon" \
      --footer "$footer" \
      --footer-icon "$footer_icon" \
| send $args

cd $previous_directory
