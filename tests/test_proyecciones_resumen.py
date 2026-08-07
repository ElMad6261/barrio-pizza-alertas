import pandas as pd
import pytest

from app.core.alertas import calcular_necesidad_y_orden, construir_resumen_proyecciones
from app.core.data_loader import cargar_consumo_historico, cargar_ingredientes, cargar_inventario, cargar_orden
from app.core.unidades import construir_tabla_conversion


@pytest.fixture(scope="module")
def datos():
    return {
        "ingredientes": cargar_ingredientes(),
        "inventario": cargar_inventario(),
        "orden": cargar_orden(),
        "consumo": cargar_consumo_historico(),
    }


@pytest.fixture(scope="module")
def resumen_proyecciones(datos):
    tabla_conversion = construir_tabla_conversion(datos["ingredientes"])
    df = calcular_necesidad_y_orden(datos["ingredientes"], datos["inventario"], datos["orden"], datos["consumo"])
    return construir_resumen_proyecciones(df, tabla_conversion)


def test_cubre_las_88_combinaciones(resumen_proyecciones):
    assert len(resumen_proyecciones) == 4 * 22


def test_todas_las_filas_tienen_ingrediente_id_e_ingrediente_nombre(resumen_proyecciones):
    for fila in resumen_proyecciones:
        assert fila["ingrediente_id"]
        assert fila["ingrediente"]
        assert fila["ingrediente_id"] != fila["ingrediente"]  # nombre legible, no el id crudo


def test_harina_costa_del_este_tiene_r2_alto(resumen_proyecciones):
    fila = next(
        f for f in resumen_proyecciones if f["sucursal"] == "Costa del Este" and f["ingrediente_id"] == "harina"
    )
    assert fila["metodo"] == "tendencia"
    assert fila["r2"] > 0.95


def test_pepperoni_marbella_tiene_semana_3_excluida(resumen_proyecciones):
    fila = next(
        f for f in resumen_proyecciones if f["sucursal"] == "Marbella" and f["ingrediente_id"] == "pepperoni"
    )
    assert 3 in fila["semanas_excluidas"]


def test_r2_nunca_es_nan_en_este_dataset(resumen_proyecciones):
    # Con solo 6 semanas y máximo 1-2 outliers reales en este dataset,
    # siempre hay suficientes puntos para intentar un ajuste.
    for fila in resumen_proyecciones:
        assert fila["r2"] is None or not pd.isna(fila["r2"])
