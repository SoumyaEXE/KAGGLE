"""Base story: a dental clinic patient portal."""

from __future__ import annotations

from .common import BaseStory

STORY = BaseStory(
    scenario_id="clinic-portal",
    org_name="BrightSmile Dental",
    service_name="Patient Portal",
    host_example="brightsmile-dental-portal.example",
    sandbox="eval-sandbox",
    record_type="patient",
    record_label="Patient",
    other_org="Northwind Analytics Co.",
    invented_registered_since=2011,
)
