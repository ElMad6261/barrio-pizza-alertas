from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


def test_health_check():
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_alertas_devuelve_resumen_real():
    response = client.get("/api/alertas")
    assert response.status_code == 200
    data = response.json()

    assert data["total_alertas"] == len(data["alertas"])
    # Con los datos reales del reto: 1 olvidado, 1 quiebre, 2 sobre-pedido,
    # 1 ingrediente desconocido (aji_chombo) = 5 alertas en total.
    assert data["total_alertas"] == 5
    assert data["insumos_olvidados"] == 1
    assert data["riesgo_quiebre"] == 1
    assert data["sobre_pedido"] == 2
    assert data["ingredientes_desconocidos"] == 1


def test_alertas_por_sucursal_filtra_correctamente():
    response = client.get("/api/alertas/Brisas del Golf")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2  # mozzarella olvidada + cebolla sobre-pedido
    assert all(a["sucursal"] == "Brisas del Golf" for a in data)


def test_alertas_por_sucursal_sin_resultados():
    response = client.get("/api/alertas/Sucursal Inexistente")
    assert response.status_code == 200
    assert response.json() == []


def test_proyeccion_devuelve_detalle_real():
    response = client.get("/api/proyeccion/Costa del Este/harina")
    assert response.status_code == 200
    data = response.json()
    assert data["metodo"] == "tendencia"
    assert data["consumo_proyectado"] > 300


def test_proyeccion_ingrediente_inexistente_devuelve_404():
    response = client.get("/api/proyeccion/Costa del Este/ingrediente_falso")
    assert response.status_code == 404
