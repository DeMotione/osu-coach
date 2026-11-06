"""The constants of Star-Scale IRT (``docs/star-scale-irt.md``). All but the anchor probabilities are priors, unfitted
until the validation steps (spec §11) are run on real players."""

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
# accuracy: at θ = b, 88% of hit single notes are 300s. The spec's 95% is unfitted and far stricter than players
# are: a typical 6★ player's single notes are ~12% non-300 (the Comfort-Based engine's reference at its level), so
# with 95% every typical player's accuracy read 2–3★ below their level
A_ACC, PI_ACC = 0.527, 0.88
C_ACC = math.log(PI_ACC / (1 - PI_ACC))
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
DENSITY_REF, K_DENSITY = 4.0, 0.5  # ★ per doubling of the notes visible at once above DENSITY_REF (fix 12)
K_SL = 0.5  # ★ per doubling of slider shape x speed change
SLIDER_FOLLOW_SLACK = 1.0  # circle diameters of slider path the follow circle covers: shorter sliders aren't items
LAMBDA = 0.35  # a hard pattern also makes 300s harder
ROUND = 0.05  # ★: item difficulties are grouped to this

TAU = 1.5  # prior SD of every θ (★) around the comfort level
DELTA_SD = 0.5  # prior SD of the session drop δ
ALPHA, BETA = 2.0, 998.0  # Beta prior of the lapse rate ε
EPS0 = 0.002
D = 2.0  # design effect: notes within a play are not independent
FORM_SD = 0.25  # ★: play-to-play form, added to the ranges (fix 6)

# item classes (spec §3.0) and kinds of group
J, S, DEEP, F, SL, AC = range(6)
HEAD, SLIDER, ACCURACY = range(3)
STREAM_GAP_MS = 200.0  # notes this close keep a tapping section going ...
STAMINA_S = 30.0  # ... and notes this long into one test stamina as well as run_pos >= 16 does (fix 11)

# display states (spec §9)
MEASURED_SE, PROVISIONAL_SE = 0.35, 0.75
Z90 = 1.6448536269514722
MODE_GAP, MODE_LOGLIK = 0.3, 2.0  # modes this far apart (★) and this close in fit are both answers (fix 5)
