from app.cities import CITY_NAMES, MYANMAR_CITIES


def test_every_entry_has_required_fields():
    for entry in MYANMAR_CITIES:
        assert set(entry.keys()) == {"city", "state", "zip"}
        assert entry["city"].strip()
        assert entry["state"].strip()
        assert entry["zip"].strip()


def test_no_duplicate_city_names():
    names = [entry["city"].lower() for entry in MYANMAR_CITIES]
    assert len(names) == len(set(names)), "a city appears more than once"


def test_city_names_lookup_matches_data():
    assert len(CITY_NAMES) == len(MYANMAR_CITIES)
    for entry in MYANMAR_CITIES:
        assert entry["city"].lower() in CITY_NAMES
