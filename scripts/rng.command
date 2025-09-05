#!/bin/argparse --store
! rng
@ Return random number from sequence.
% %(prog)s [start] <stop> [step]
; start | nargs ? | type int | help start number | default 0
; stop | type int | help end number
; step | nargs ? | type int | help step to go with | default 1
|||

segment $start:$stop:$step | pick
