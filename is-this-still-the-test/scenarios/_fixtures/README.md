# scenarios/_fixtures (LOCAL TEST FIXTURES ONLY)

These files are **NOT real download snapshots**. They exist only so stream B can
build and self-test the `scenarios` package before stream A's real
`data/sources/**` files land. They mimic the format described in CONTRACTS.md
(section "A -> B").

They are used **only** when `build_all(..., use_fixtures=True)` is passed, or when
the environment variable `SCENARIOS_USE_FIXTURES=1` is set, AND the real
`data/sources/` files are absent. The real build (`build_all()` with defaults)
reads `data/sources/` and never touches this directory.

Do not ship these as if they were the real, dated, hashed snapshots.
