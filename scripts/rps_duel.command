#!/bin/argparse --store
! rps_duel
@ Play rock-paper-scissors with somebody.
% %(prog)s <opponent>
; opponent | type id | help any user
|||

params return_on_error
array scissors rock paper | storage names

{
    echo "You've initiated duel with **$(< /get/$opponent/.str)**!"
    echo "Please, pick either \`rock\`, \`paper\` or \`scissors\` within 30 s."
} | send -UD | storage msg -l

read -c scissors rock paper -m $msg -t 30 | storage object
{
    storage names
    pointer -r $object
} | get | storage player_value -l

{
    echo "You've been asked for a duel with **$(< /current/user/.str)**!"
    echo "Please, pick either \`rock\`, \`paper\` or \`scissors\` within 30 s."
} | send -Uc $opponent | storage msg -l

read -c scissors rock paper -m $msg -t 30 -u $opponent | storage enemy
{
    storage names
    pointer -r $enemy
} | get | storage enemy_value -l

if [ enemy_value == player_value ]; then
    echo "Draw: [$object] vs [$enemy]"
elif [ \
    player_value < enemy_value \
    and [player_value, enemy_value] != [0, 2] \
    or [player_value, enemy_value] == [2, 0] \
]; then
    echo "$(< /get/$opponent/.str) wins: $object vs [$enemy]"
else
    echo "$(< /current/user/.str) wins: [$object] vs $enemy"
fi
