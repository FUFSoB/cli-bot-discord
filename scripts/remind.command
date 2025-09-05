#!/bin/argparse --store --merge
! remind
@ Send you message after some time.
% %(prog)s <time> [text*]
; time | type time | help time to sleep
; text | default something | nargs * | help any text to send after time
; -d --direct-message | action store_true | help send everything in DMs
; -R --reply | action store_true | dest reply
             | help send as reply to your message
|||

params return_on_error
{
    date -R
    timedelta $time
} | datedelta -s | storage on

if [ direct_message ]; then
    schedule $time -c "echo You asked me to remind you about **$text** | send -D"
    echo "You'll be reminded on $on." | send -DF
else
    if [ reply ]; then
        schedule $time -c "echo You asked me to remind you about that message. | send -R --reply-mention"
    else
        schedule $time -c "echo $(< /current/user/mention), you asked me to remind you about **$text** | send"
    fi
    echo "You'll be reminded on $on." | send -F
fi
