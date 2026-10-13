# osu-coach (core)

The domain of osu! coach: everything that turns replay files into numbers and advice. No web code lives
here; the HTTP API (`../api`) and the web app (`../frontend`) are layers on top of this package.

| Module | What it does |
| --- | --- |
| `osr`, `beatmap`, `curves` | Parse `.osr` replays (stable + lazer) and `.osu` beatmaps, slider paths |
| `judge`, `judge_lazer` | Re-simulate every judgement with the rules of the client that recorded the replay |
| `features`, `difficulty`, `analysis` | Per-note pattern features, local difficulty (rosu-pp), one replay's analysis |
| `locate`, `library`, `sources` | Find osu! installs, scan replays, look up / download beatmaps, cached analysis |
| `selection` | Date windows and *All* / *Best* replay sets |
| `profile` | Aggregate many analyses into skill scores, miss causes, aim / tapping / slider statistics |
| `insights` | Chart-ready aggregations of a profile and of one play (heat maps, histograms, binned rates) |
| `advice`, `goals` | Tips, setup suggestions (tablet area, sensitivity, rapid trigger, SayoDevice), skill goals |
| `check` | One replay on its own: misses with timestamps, clusters to practise, comparison with other plays |
| `progress` | History by month / week / day in SQLite |
| `pool`, `collection_db`, `lazer_import` | Map pool, suggestions, playlists, `collection.db`, lazer import folder |
| `cli` | The `osu-coach` command line |

```
pip install -e ".[dev]"
pytest
ruff check .
```

`dev_tools/` holds the scripts used to build the map pool and validate the simulation; they are not
part of the package.
