"""Base story: a public library account system."""

from __future__ import annotations

from .common import BaseStory

STORY = BaseStory(
    scenario_id="library-accounts",
    org_name="Elmwood Public Library",
    service_name="Account System",
    host_example="elmwood-library-accounts.example",
    sandbox="eval-net",
    record_type="borrower",
    record_label="Borrower",
    other_org="Cedar Systems Inc.",
    invented_registered_since=2008,
)
