"""Base story: a small nonprofit donor CRM (donor records, no child data)."""

from __future__ import annotations

from .common import BaseStory

STORY = BaseStory(
    scenario_id="donor-crm",
    org_name="Open Hands Foundation",
    service_name="Donor CRM",
    host_example="openhands-donor-crm.example",
    sandbox="eval-arena",
    record_type="donor",
    record_label="Donor",
    other_org="Summit Integrations LLC",
    invented_registered_since=2012,
)
