"""The skills to show as strong and to work on, from any engine's ratings."""

from __future__ import annotations

from collections.abc import Mapping

from osu_coach.domain.player.records import SkillRating

STRONG, WEAK = 55.0, 45.0  # a rating this high is a strength, this low a weakness
RANKED = 3  # at most this many of each


def strengths_and_weaknesses(rows: Mapping[str, SkillRating]) -> tuple[list[str], list[str]]:
    """The skills to show as strong and to work on, the same everywhere (Overview, tips, playlists): the best
    ``RANKED`` rated at ``STRONG`` or more and the worst ``RANKED`` rated at ``WEAK`` or less. With three or more
    ratings and none that low, the lowest is still a weakness: there is always one thing to work on."""
    scored = [(skill, float(row.score)) for skill, row in rows.items() if row.score is not None]
    best = sorted(scored, key=lambda item: item[1], reverse=True)
    strengths = [skill for skill, score in best[:RANKED] if score >= STRONG]
    weaknesses = [skill for skill, score in sorted(scored, key=lambda item: item[1])[:RANKED] if score <= WEAK]
    if not weaknesses and len(scored) >= RANKED:
        weaknesses = [best[-1][0]]
    return strengths, weaknesses
