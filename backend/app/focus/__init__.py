"""Phase 18R event-sourced focus architecture."""

from __future__ import annotations

import sys

from app.focus.models import FocusState, TurnPlan

# Phase 21H7: disable the legacy blind event-count cap for the demo build.
# Canonical Focus state is reconstructed by replaying lifecycle events, so
# trimming the oldest events can remove the seed event for a long-lived Focus
# and make that Focus disappear on the next replay. Until snapshot-aware
# compaction exists, retaining the full event log is safer than truncating it.
#
# store.py still contains the historical _MAX_EVENTS guard; setting the cap to
# sys.maxsize here preserves the existing store implementation while making
# destructive truncation unreachable for any realistic QMeet demo session.
from app.focus import store as _store  # noqa: E402

_store._MAX_EVENTS = sys.maxsize

__all__ = ["FocusState", "TurnPlan"]
