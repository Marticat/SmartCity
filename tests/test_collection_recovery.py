import json
import pytest
import httpx
from scripts import collect_pois


def test_partial_collection_preserves_previous_snapshot(tmp_path, monkeypatch):
    raw = tmp_path / "raw/overpass_astana.json"
    raw.parent.mkdir()
    original = '{"elements":[{"existing":"snapshot"}]}'
    raw.write_text(original, encoding="utf-8")
    monkeypatch.setattr(collect_pois, "DATA_DIR", tmp_path)
    monkeypatch.setattr(collect_pois.time, "sleep", lambda _: None)
    calls = []
    def post(url, **kwargs):
        calls.append(url)
        return httpx.Response(200, request=httpx.Request("POST", url), json={
            "remark":"runtime error: timeout", "elements":[{"type":"node","id":999}]})
    monkeypatch.setattr(collect_pois.httpx, "post", post)
    with pytest.raises(RuntimeError, match="previous snapshot retained"):
        collect_pois.collect(refresh=True)
    assert raw.read_text(encoding="utf-8") == original
    assert len(calls) == 3
    assert not (tmp_path / "processed/pois.json").exists()
