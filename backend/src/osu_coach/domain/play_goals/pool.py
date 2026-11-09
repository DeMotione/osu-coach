"""The mod configurations and accuracies the play-goal pool is built for."""

from __future__ import annotations

# EZ variants (2, 10, 66, 74) come back once the shipped pool is rebuilt with them (tools/build_goal_pool.py).
CONFIGS = {
    "NM": 0,
    "HD": 8,
    "HR": 16,
    "HDHR": 24,
    "DT": 64,
    "HDDT": 72,
    "HRDT": 80,
    "HDHRDT": 88,
}
ACCURACIES = (0.9, 0.95, 0.97, 0.98, 0.99, 1.0)
