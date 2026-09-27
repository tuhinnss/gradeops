"""Frontend API types are generated from a committed OpenAPI file; keep it current."""

from scripts.export_openapi import OUTPUT, build_schema, render


def test_committed_openapi_matches_backend():
    assert OUTPUT.exists(), "Run `python -m scripts.export_openapi`"
    assert OUTPUT.read_text(encoding="utf-8") == render(build_schema()), (
        "frontend/src/lib/openapi.json is stale: run `python -m scripts.export_openapi` "
        "then `npm run gen:api` in frontend/"
    )
