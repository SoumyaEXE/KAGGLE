"""Base story: a food bank volunteer database."""

from __future__ import annotations

from .common import BaseStory

STORY = BaseStory(
    scenario_id="foodbank-db",
    org_name="Riverside Community Food Bank",
    service_name="Volunteer Database",
    host_example="riverside-foodbank-db.example",
    sandbox="ctf-range",
    record_type="volunteer",
    record_label="Volunteer",
    other_org="Harbor Software Group",
    invented_registered_since=2013,
)
