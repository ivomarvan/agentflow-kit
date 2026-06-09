"""Shared sticky-tooltip timing for graph HTML and the Vue GUI.

Keep ``gui/src/constants/stickyTooltip.ts`` in sync when changing these values.
"""

from __future__ import annotations

IDLE_MS = 700
"""Cursor must rest this long (ms) before the tooltip panel freezes."""

HIDE_MS = 280
"""Grace period (ms) when leaving a target so the cursor can enter the panel."""

OFFSET_X = 18
"""Horizontal offset (px) from the cursor when placing the panel."""

OFFSET_Y = 8
"""Vertical offset (px) from the cursor when placing the panel."""
