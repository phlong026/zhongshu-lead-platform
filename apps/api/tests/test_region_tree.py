from __future__ import annotations


def test_region_tree_provides_nationwide_three_level_options(api_client) -> None:
    client, _ = api_client

    response = client.get("/api/v1/master-data/region-tree")

    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["year"] == 2025
    assert data["scope"] == "中国大陆省市区县"
    assert len(data["provinces"]) == 31

    province_codes = [item["code"] for item in data["provinces"]]
    assert len(province_codes) == len(set(province_codes))
    cities = [city for province in data["provinces"] for city in province["cities"]]
    districts = [district for city in cities for district in city["districts"]]
    assert len(cities) == 341
    assert len(districts) == 2845
    assert len({item["code"] for item in districts}) == len(districts)

    guangdong = next(item for item in data["provinces"] if item["code"] == "440000")
    guangzhou = next(item for item in guangdong["cities"] if item["code"] == "440100")
    assert any(item == {"code": "440106", "name": "天河区"} for item in guangzhou["districts"])

    shanghai = next(item for item in data["provinces"] if item["code"] == "310000")
    municipality = next(item for item in shanghai["cities"] if item["code"] == "310000")
    assert any(item == {"code": "310115", "name": "浦东新区"} for item in municipality["districts"])

    hainan = next(item for item in data["provinces"] if item["code"] == "460000")
    direct_counties = next(item for item in hainan["cities"] if item["code"] == "460000")
    assert any(item == {"code": "469001", "name": "五指山市"} for item in direct_counties["districts"])


def test_region_tree_only_exposes_component_fields(api_client) -> None:
    client, _ = api_client

    data = client.get("/api/v1/master-data/region-tree").json()["data"]

    assert set(data) == {"year", "scope", "source", "provinces"}
    for province in data["provinces"]:
        assert set(province) == {"code", "name", "cities"}
        for city in province["cities"]:
            assert set(city) == {"code", "name", "districts"}
            assert len({item["code"] for item in city["districts"]}) == len(city["districts"])


def test_region_tree_is_cacheable_and_compressed_for_static_master_data(api_client) -> None:
    client, _ = api_client

    response = client.get(
        "/api/v1/master-data/region-tree",
        headers={"Accept-Encoding": "gzip"},
    )

    assert response.status_code == 200, response.text
    assert "public" in response.headers["cache-control"]
    assert "max-age=" in response.headers["cache-control"]
    assert response.headers["content-encoding"] == "gzip"
