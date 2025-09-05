#!/bin/argparse --store
! rps
@ Play rock-paper-scissors game with a bot!
% %(prog)s [object]
; object | nargs ? | choices rock paper scissors | help object to play with
|||

array scissors rock paper | storage names

if [ not object or object not in ["rock", "paper", "scissors"] ]; then
    object=$(storage names | pick)
fi

{ storage names; pointer -r $object; } | get | storage player_value -l

enemy=$(storage names | pick)
{ storage names; pointer -r $enemy; } | get | storage enemy_value -l

if [ enemy_value == player_value ]; then
    echo "Draw: [$object] vs [$enemy]"
elif [ \
    player_value < enemy_value \
    and [player_value, enemy_value] != [0, 2] \
    or [player_value, enemy_value] == [2, 0] \
]; then
    echo "You lose: $object vs [$enemy]"
else
    echo "You win: [$object] vs $enemy"
fi
