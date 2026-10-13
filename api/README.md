# osu-coach-api

The HTTP API of osu! coach, built with FastAPI. It sits between the domain package (`../core`, imported as
`osu_coach`) and the web app (`../frontend`) and also serves the built web app.

```
pip install -e ../core -e ".[dev]"
osu-coach-api            # http://localhost:8501 (add --open to open the browser)
pytest
ruff check .
```

* **API reference (Scalar):** http://localhost:8501/docs, OpenAPI document at `/api/openapi.json`.
* **Only for this computer:** the server binds to 127.0.0.1, answers only to `localhost` / `127.0.0.1` host
  names, and refuses state-changing requests coming from other web sites (`security.py`).
* **State:** one user, one process. The scanned library, the analysed replays and the profile live in a
  `Workspace` (`workspace.py`); remembered choices are in the domain's `settings.json`, shared with the
  `osu-coach` command line.
* **Slow work** (scanning, analysing, downloading) runs as background jobs (`jobs.py`): the endpoint answers
  `202` with a job, `GET /api/jobs/{id}` reports progress and the typed result.

| Module | |
| --- | --- |
| `app.py` | `create_app()`: routers, error handlers, middleware, Scalar docs, web app |
| `routers/` | Endpoints, one module per area (thin: validation and HTTP only) |
| `services/` | The work behind them: domain calls and their results as response models |
| `schemas/` | Request / response models — the OpenAPI document and the web app's types |
| `workspace.py`, `jobs.py` | Session state; background jobs and the busy gate |
| `server.py` | `osu-coach ui` / `osu-coach-api`: uvicorn on localhost, opens the browser |
| `openapi.py` | Writes the OpenAPI document for the web app's generated types |

After changing a schema, regenerate the web app's types:

```
python -m osu_coach_api.openapi ../frontend/src/api/openapi.json
cd ../frontend && npm run gen:api
```

`tests/test_openapi_contract.py` fails while the committed document is out of date.
