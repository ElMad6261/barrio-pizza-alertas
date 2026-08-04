from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


def test_health_check():
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_alertas_devuelve_resumen():
    response = client.get("/api/alertas")
    assert response.status_code == 200
    data = response.json()
    assert "alertas" in data
    assert "total_alertas" in data
    assert data["total_alertas"] == len(data["alertas"])
