from backend.app.retrieval import Store


def test_named_location_precedes_description_only_match(tmp_path, monkeypatch, poi_factory):
    museum = poi_factory(id="osm:node:1", name="Қазақша атауы",
                         alternative_names=["Национальный музей Республики Казахстан", "Национальный музей"])
    incidental = poi_factory(id="osm:node:2", name="Другой музей")
    store = Store(tmp_path)
    store.pois = [incidental, museum]
    store.by_id = {p.id: p for p in store.pois}
    monkeypatch.setattr(store, "lexical", lambda query: [incidental.id, museum.id])
    assert store.locations("Национальный музей", 1)[0].id == museum.id


def test_name_search_works_without_index(tmp_path, poi_factory):
    museum = poi_factory(id="osm:node:1", name="Қазақша атауы",
                         alternative_names=["Национальный музей"])
    store = Store(tmp_path)
    store.pois = [museum]
    store.by_id = {museum.id: museum}
    assert store.locations("Национальный музей", 1)[0].id == museum.id
