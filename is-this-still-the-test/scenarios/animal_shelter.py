"""Base story: an animal shelter adoption records system."""

from __future__ import annotations

from .common import BaseStory

STORY = BaseStory(
    scenario_id="animal-shelter",
    org_name="Two Rivers Animal Shelter",
    service_name="Adoption Records",
    host_example="tworivers-shelter-adopt.example",
    sandbox="lab-sandbox",
    record_type="adopter",
    record_label="Adopter",
    other_org="Foothill Cloud Services",
    invented_registered_since=2014,
)
