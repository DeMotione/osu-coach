"""The model's constants; most are unfitted priors."""

from __future__ import annotations

import math

import numpy as np

# the skills of the joint fit, in this order (accuracy is fitted on its own), and their names in the app
SKILLS = ("aim", "flow", "tap", "stam", "read", "sl")
APP_KEYS = {
    "aim": "aim",
    "flow": "flow_aim",
    "tap": "speed",
    "stam": "stamina",
    "read": "reading",
    "sl": "sliders",
    "acc": "accuracy",
}
ANCHOR_OF = {"aim": "aim", "flow": "aim", "tap": "spd", "stam": "spd", "read": "read", "sl": "sl", "acc": "acc"}

A = np.array([1.6, 1.6, 2.0, 2.0, 1.2, 1.0])  # discrimination a_k (per ★)
PI = 0.98  # each skill fails on 2% of notes at θ = b: this defines the scale
C = math.log(PI / (1 - PI))
# accuracy: 90% 300s at θ = b (the spec's 95% read every typical player 2–3★ too low)
A_ACC, PI_ACC = 0.527, 0.90
C_ACC = math.log(PI_ACC / (1 - PI_ACC))
# timing of hit stream notes: 3% 50s at θ = b, weakly tied to tempo
A_TIMING, PI_TIMING = 1.0, 0.97
C_TIMING = math.log(PI_TIMING / (1 - PI_TIMING))
GIVE_UP_RUN = 20  # heads missed in a row with no input: the player stopped playing there
SESSION_SHIFT = np.array([1, 1, 1, 1, 1, 0], dtype=float)  # δ lowers every skill but sliders (and accuracy)

# miss classes A (aim), B (behind: late or lost), T (early, no tap, notelock): the mix each skill's misses have
E = np.array(
    [
        [0.75, 0.25, 0.00],  # aim
        [0.80, 0.20, 0.00],  # flow
        [0.10, 0.40, 0.50],  # tap
        [0.05, 0.45, 0.50],  # stam
        [0.50, 0.20, 0.30],  # read
        [1.00, 0.00, 0.00],  # sl (slider breaks: one class)
    ]
)
E0 = np.array([0.40, 0.30, 0.30])  # random lapses

H_HD, H_FL = 0.5, 1.5  # ★ added to reading difficulty
DENSITY_REF, K_DENSITY = 4.0, 0.5  # ★ per doubling of the notes visible at once above DENSITY_REF
K_SL = 0.5  # ★ per doubling of slider shape x speed change
K_SL_SPEED = 1.0  # ★ per doubling of a slider's speed over its map's usual moving slider (a prior)
SL_SPEED_RANGE = 2.0  # ... counted up to 4x faster or slower
SLIDER_FOLLOW_SLACK = 1.0  # circle diameters of slider path the follow circle covers: shorter sliders aren't items
LAMBDA = 0.35  # a hard pattern also makes 300s harder
ROUND = 0.05  # ★: item difficulties are grouped to this

TAU = 1.5  # prior SD of every θ (★) around the comfort level
DELTA_SD = 0.5  # prior SD of the session drop δ
ALPHA, BETA = 2.0, 998.0  # Beta prior of the lapse rate ε
EPS0 = 0.002
D = 2.0  # design effect: notes within a play are not independent (the spec's, used without per-play clusters)
# clustered variances are still too narrow: factor fitted by split halves on one player (refit on more)
D_CLUSTER = 2.0
FORM_SD = 0.25  # ★: play-to-play form, added to the ranges when no per-play groups are given

# item classes (spec §3.0) and kinds of group
J, S, DEEP, F, SL, AC = range(6)
HEAD, SLIDER, ACCURACY, TIMING = range(4)
STREAM_GAP_MS = 200.0  # notes this close keep a tapping section going ...
STAMINA_S = 30.0  # ... and notes this long into one test stamina as well as run_pos >= 16 does

# display states (spec §9)
MEASURED_SE, PROVISIONAL_SE = 0.35, 0.75
Z90 = 1.6448536269514722
MODE_GAP, MODE_LOGLIK = 0.3, 2.0  # modes this far apart (★) and this close in fit are both answers
