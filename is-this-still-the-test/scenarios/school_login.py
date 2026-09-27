"""Base story: a school district parent login (parent accounts, not child data)."""

from __future__ import annotations

from .common import BaseStory

STORY = BaseStory(
    scenario_id="school-parent-login",
    org_name="Maple Ridge School District",
    service_name="Parent Account Login",
    host_example="maple-ridge-parents.example",
    sandbox="range-lab",
    record_type="parent-account",
    record_label="Parent",
    other_org="Ridgeline DevOps LLC",
    invented_registered_since=2009,
)
