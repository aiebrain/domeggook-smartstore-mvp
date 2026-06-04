import httpx
import pytest

from app.main import app
from tests.test_extractor import SAMPLE_HTML


def make_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver")


@pytest.mark.anyio
async def test_health():
    async with make_client() as client:
        response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.anyio
async def test_cors_allows_local_nextjs_frontend():
    async with make_client() as client:
        response = await client.options(
            "/api/analyze",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "POST",
            },
        )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"


@pytest.mark.anyio
async def test_cors_allows_wsl_ip_windows_frontend():
    async with make_client() as client:
        response = await client.options(
            "/api/analyze",
            headers={
                "Origin": "http://192.168.168.150:3001",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            },
        )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://192.168.168.150:3001"


@pytest.mark.anyio
async def test_analyze_with_supplied_html_smoke():
    async with make_client() as client:
        response = await client.post(
            "/api/analyze",
            json={"url": "https://domeggook.com/54804743", "html": SAMPLE_HTML},
        )
    assert response.status_code == 200
    data = response.json()
    assert data["product"]["product_no"] == "54804743"
    assert data["smartstore_package"]["sale_price_recommendation"] == 11600
    assert data["smartstore_package"]["qa_flags"] == []
    assert data["smartstore_package"]["registration_draft"]["source_raw"]["product_no"] == "54804743"
    assert data["smartstore_package"]["registration_draft"]["smartstore_draft"]["origin_product"]["sale_price"] == 11600
    assert "집게" in data["smartstore_package"]["registration_draft"]["smartstore_draft"]["seo"]["tags"]
    assert data["smartstore_package"]["individual_product"]["search_tags"]
    assert data["smartstore_package"]["registration_draft"]["qa"]["status"] == "NEED_REVIEW"


@pytest.mark.anyio
async def test_analyze_rejects_bad_url():
    async with make_client() as client:
        response = await client.post("/api/analyze", json={"url": "https://example.com/1", "html": "<html></html>"})
    assert response.status_code == 400
    assert "Domeggook" in response.json()["detail"]
