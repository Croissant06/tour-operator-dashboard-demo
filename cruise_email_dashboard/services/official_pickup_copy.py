from __future__ import annotations

from datetime import time


OFFICIAL_PICKUP_DESCRIPTIONS = {
    "Harbor Pier Stop": "the curbside stop beside the main harbor pier",
    "Marina Walk Stop": "the passenger loading area by Marina Walk",
    "Sunset Boulevard Stop": "the marked shuttle stop on Sunset Boulevard",
    "Seaside Market Stop": "the pickup bay outside Seaside Market",
    "Lighthouse Point Stop": "the roadside stop below Lighthouse Point",
    "Coral Plaza Stop": "the shuttle bay at Coral Plaza",
    "Reefside Market Stop": "the signed pickup bay beside Reefside Market",
    "Lagoon Avenue Stop": "the sheltered stop on Lagoon Avenue",
    "Cove Boardwalk Stop": "the passenger zone at the Cove Boardwalk entrance",
    "Tidepool Gardens Stop": "the loading area outside Tidepool Gardens",
}


def render_official_pickup_copy(stop_name: str, language: str, pickup_time: str, cruise_time: time | None = None) -> str | None:
    description = OFFICIAL_PICKUP_DESCRIPTIONS.get(stop_name)
    if not description:
        return None
    return (
        "Please find attached the pickup point you have selected. "
        f"The pickup point is {description}. "
        f"Our transport will be there at {pickup_time} to collect you."
    )
