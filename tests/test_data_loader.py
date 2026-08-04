import pandas as pd
import pytest

from app.core.data_loader import (
    cargar_consumo_historico,
    cargar_ingredientes,
    cargar_inventario,
    cargar_orden,
    validar_datos,
)


@pytest.fixture(scope="module")
def datos():
    return {
        "ingredientes": cargar_ingredientes(),
        "inventario": cargar_inventario(),
        "orden": cargar_orden(),
        "consumo": cargar_consumo_historico(),
    }


def test_carga_las_4_sucursales(datos):
    sucursales = set(datos["inventario"]["sucursal"])
    assert sucursales == {"Brisas del Golf", "Costa del Este", "Marbella", "Via Argentina"}


def test_carga_22_ingredientes(datos):
    assert len(datos["ingredientes"]) == 22


def test_es_perecedero_se_convierte_a_booleano(datos):
    assert datos["ingredientes"]["es_perecedero"].dtype == bool


def test_historico_tiene_6_semanas_por_combo(datos):
    conteo = datos["consumo"].groupby(["sucursal", "ingrediente_id"]).size()
    assert (conteo == 6).all()


def test_detecta_insumo_olvidado_mozzarella_brisas(datos):
    reporte = validar_datos(
        datos["ingredientes"], datos["inventario"], datos["orden"], datos["consumo"]
    )
    faltantes = {(f["sucursal"], f["ingrediente_id"]) for f in reporte.combos_faltantes_en_orden}
    assert ("Brisas del Golf", "mozzarella") in faltantes


def test_detecta_ingrediente_desconocido_aji_chombo(datos):
    reporte = validar_datos(
        datos["ingredientes"], datos["inventario"], datos["orden"], datos["consumo"]
    )
    desconocidos = {
        (d["sucursal"], d["ingrediente_id"])
        for d in reporte.ingredientes_desconocidos
        if d["archivo"] == "orden"
    }
    assert ("Costa del Este", "aji_chombo") in desconocidos


def test_inventario_no_tiene_combos_faltantes(datos):
    reporte = validar_datos(
        datos["ingredientes"], datos["inventario"], datos["orden"], datos["consumo"]
    )
    assert reporte.combos_faltantes_en_inventario == []


def test_no_hay_valores_negativos(datos):
    reporte = validar_datos(
        datos["ingredientes"], datos["inventario"], datos["orden"], datos["consumo"]
    )
    assert reporte.valores_negativos == []
