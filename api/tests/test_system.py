"""Health, labels, docs, serving the web app, and the local-only protections."""
from conftest import make_client

from osu_coach.profile import SKILL_HELP, SKILL_LABELS


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok" and body["version"] and body["core_version"]


def test_meta_has_every_skill_with_its_explanation(client):
    m = client.get("/api/meta").json()
    assert [s["key"] for s in m["skills"]] == list(SKILL_LABELS)
    for s in m["skills"]:
        assert (s["what"], s["how"], s["practise"]) == SKILL_HELP[s["key"]]
    assert m["latest_choices"] == [100, 500, 1000, 0]
    assert {c["key"] for c in m["date_choices"]} == {"all", "session", "7d", "30d", "custom"}
    assert len(m["lazer_instructions"]) == 3


def test_openapi_and_scalar_docs(client):
    spec = client.get("/api/openapi.json").json()
    assert spec["info"]["title"] == "osu! coach API"
    assert "/api/profile/overview" in spec["paths"] and "/api/jobs/{job_id}" in spec["paths"]
    # a job's result is typed by its kind
    job = spec["components"]["schemas"]["AnalysisJob"]
    assert job["properties"]["kind"]["const"] == "analysis"
    docs = client.get("/docs")
    assert docs.status_code == 200 and "text/html" in docs.headers["content-type"]
    assert "@scalar/api-reference@" in docs.text and "/api/openapi.json" in docs.text


def test_unknown_api_path_is_a_json_404(client):
    r = client.get("/api/nope")
    assert r.status_code == 404 and r.json()["code"] == "not_found"


def test_without_a_built_web_app_the_root_says_how_to_build_it(tmp_path):
    with make_client(tmp_path / "cache", web_dir=tmp_path / "not-built") as c:
        assert c.get("/api/health").json()["web_app"] is False
        r = c.get("/overview")
        assert r.status_code == 200 and "npm run build" in r.text and 'href="/docs"' in r.text


def test_serves_the_web_app_with_client_side_routes(tmp_path):
    web = tmp_path / "web"
    (web / "assets").mkdir(parents=True)
    (web / "index.html").write_text("<!doctype html><title>osu! coach</title>")
    (web / "assets" / "app-1234.js").write_text("console.log(1)")
    (web / "sw.js").write_text("self")
    (tmp_path / "secret.txt").write_text("secret")
    with make_client(tmp_path / "cache", web_dir=web) as c:
        assert c.get("/api/health").json()["web_app"] is True
        index = c.get("/")
        assert index.status_code == 200 and "osu! coach" in index.text
        assert index.headers["cache-control"] == "no-cache"
        assert "osu! coach" in c.get("/overview").text                         # a client-side route
        asset = c.get("/assets/app-1234.js")
        assert asset.text == "console.log(1)" and "immutable" in asset.headers["cache-control"]
        assert c.get("/sw.js").headers["cache-control"] == "no-cache"
        # fixed content types, not the system's guess (Windows often says text/plain for .js)
        assert asset.headers["content-type"].startswith("text/javascript")
        (web / "manifest.webmanifest").write_text("{}")
        assert c.get("/manifest.webmanifest").headers["content-type"] == "application/manifest+json"
        assert index.headers["content-type"].startswith("text/html")
        leak = c.get("/..%2Fsecret.txt")
        assert "secret" not in leak.text


def test_other_host_names_are_refused(client):
    r = client.get("/api/health", headers={"host": "evil.example"})
    assert r.status_code == 400 and r.json()["code"] == "invalid_host"
    assert client.get("/api/health", headers={"host": "localhost:8501"}).status_code == 200
    assert client.get("/api/health", headers={"host": "127.0.0.1:8501"}).status_code == 200
    assert client.get("/api/health", headers={"host": "[::1]:8501"}).status_code == 200


def test_other_web_sites_cant_change_anything(client):
    body = {"latest": 100}
    r = client.patch("/api/settings", json=body, headers={"origin": "https://evil.example"})
    assert r.status_code == 403 and r.json()["code"] == "cross_origin"
    assert client.get("/api/settings").json()["latest"] == 500
    assert client.patch("/api/settings", json=body, headers={"origin": "http://localhost:5173"}).status_code == 200
    assert client.patch("/api/settings", json={"latest": 0}).status_code == 200            # no Origin: not a browser
    # reading is fine: the browser keeps other sites from seeing the answer
    assert client.get("/api/settings", headers={"origin": "https://evil.example"}).status_code == 200


def test_validation_errors_have_the_common_shape(client):
    r = client.patch("/api/settings", json={"latest": 7})
    assert r.status_code == 422
    body = r.json()
    assert body["code"] == "validation_error" and "latest" in body["detail"]
    r = client.patch("/api/settings", json={"no_such_setting": 1})
    assert r.status_code == 422 and r.json()["code"] == "validation_error"
