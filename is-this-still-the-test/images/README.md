# Images in the DEV post

## Kaggle screenshots (you add these)

1. Take each screenshot at full browser width, crop to the content, and save it as a PNG.
2. Upload each one through the DEV editor's "Upload image" button.
3. Paste the `https://dev-to-uploads.s3.amazonaws.com/...` URL into the `url` field of that slot in [kaggle_links.json](kaggle_links.json).
4. Run `python tools/render_post.py`.

A slot with an empty `url` is left out of the rendered post, so it's safe to publish with only some of them filled.

| Slot | Screenshot | Where it appears in the post |
|---|---|---|
| `benchmark_page` | The benchmark page, kaggle.com/benchmarks/soumyaexe/is-this-still-the-test, showing both tasks and the leaderboard | "How it runs on Kaggle Benchmarks", before the run command |
| `task_runs` | The scorecard task's run history: one row per model per daily run | Same section, after `kaggle b t status` |
| `round2_leaderboard` | The leaderboard of the `itst-round2-pilot` task | Round 2, before point 3 (the leaderboard turns upside down) |
| `transcript` | One round-2 run opened on Kaggle, showing the prompt and the JSON answer (clinic-portal L4 works best) | "Try it on your favourite model", after the prompt |


## Generated charts (in `images/charts/`)

These are rebuilt by `python tools/refresh_all.py`, which also copies them here from `figures/` (that folder is gitignored). Upload them with `python tools/dev_images.py prepare`, then `fill`.

| # | File | Section |
|---|---|---|
| cover | `figures/final/01_cover.png` | Cover image |
| 1 | `figures/final/02_how_it_works.png` | What I benchmarked, after the rung table |
| 2 | `figures/final/03_ladder.png` | Finding 1 |
| 3 | `figures/final/04_per_model.png` | Finding 1 |
| 4 | `figures/final/05_silent_stop.png` | Finding 2: the Silent Stop |
| 5 | `figures/final/06_conditions.png` | Finding 3 |
| 6 | `figures/final/07_mitigation.png` | Finding 4 |
| 7 | `figures/final/08_leaderboard.png` | The leaderboard |
| 8 | `figures/final/09_replication.png` | Does it replicate? |
| 9 | `figures/final/10_generations.png` | Newer isn't automatically better |
| 10 | `figures/pilot/11_round2_threshold.png` | Round 2 |

`figures/pilot/pilot_in_scope_ladder.png` is rendered but not used in the post (it shows the same data as Figure 10).

Before publishing, check that `grep -c "<UPLOAD" post/dev_post_final.md` prints 0 after `python tools/dev_images.py fill`.
