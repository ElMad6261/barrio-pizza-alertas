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


def test_alertas_por_sucursal_sucursal_inexistente_devuelve_404():
    response = client.get("/api/alertas/Sucursal Inexistente")
    assert response.status_code == 404
    assert "Sucursal Inexistente" in response.json()["detail"]


def test_sucursales_devuelve_las_4_reales():
    response = client.get("/api/sucursales")
    assert response.status_code == 200
    assert response.json() == ["Brisas del Golf", "Costa del Este", "Marbella", "Via Argentina"]


def test_proveedores_devuelve_los_8_reales():
    response = client.get("/api/proveedores")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 8
    assert data == sorted(data)  # alfabético
    assert "Molinos Central" in data


def test_ingredientes_devuelve_los_22_del_catalogo():
    response = client.get("/api/ingredientes")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 22
    assert all({"ingrediente_id", "nombre", "proveedor", "unidad_base", "formato_compra", "es_perecedero"} <= set(item) for item in data)


def test_proyeccion_sucursal_inexistente_devuelve_404():
    response = client.get("/api/proyeccion/Sucursal Inexistente/harina")
    assert response.status_code == 404
    assert "Sucursal Inexistente" in response.json()["detail"]


def test_proyeccion_devuelve_detalle_real():
    response = client.get("/api/proyeccion/Costa del Este/harina")
    assert response.status_code == 200
    data = response.json()
    assert data["metodo"] == "tendencia"
    assert data["consumo_proyectado"] > 300
    assert data["r2"] > 0.95
    assert data["ingrediente_id"] == "harina"


def test_proyeccion_detalle_incluye_historico_de_6_semanas():
    response = client.get("/api/proyeccion/Costa del Este/harina")
    data = response.json()
    assert len(data["historico"]) == 6
    assert [p["semana"] for p in data["historico"]] == [1, 2, 3, 4, 5, 6]
    assert not any(p["es_outlier"] for p in data["historico"])  # sin outliers en esta serie


def test_proyeccion_detalle_marca_el_outlier_en_el_historico():
    response = client.get("/api/proyeccion/Marbella/pepperoni")
    data = response.json()
    punto_semana_3 = next(p for p in data["historico"] if p["semana"] == 3)
    assert punto_semana_3["es_outlier"] is True
    assert 3 in data["semanas_excluidas"]


def test_proyeccion_ingrediente_inexistente_devuelve_404():
    response = client.get("/api/proyeccion/Costa del Este/ingrediente_falso")
    assert response.status_code == 404


def test_proyecciones_devuelve_las_88_combinaciones():
    response = client.get("/api/proyecciones")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 88


def test_proyecciones_filtra_por_sucursal():
    response = client.get("/api/proyecciones?sucursal=Marbella")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 22
    assert all(f["sucursal"] == "Marbella" for f in data)


def test_proyecciones_sucursal_inexistente_devuelve_404():
    response = client.get("/api/proyecciones?sucursal=Sucursal Inexistente")
    assert response.status_code == 404
