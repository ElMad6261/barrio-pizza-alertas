import math

import pytest

from app.core.data_loader import cargar_ingredientes, cargar_orden
from app.core.unidades import (
    IngredienteDesconocidoError,
    agregar_columna_unidad_base,
    construir_tabla_conversion,
    formatos_a_unidad_base,
    unidad_base_a_formatos,
)


@pytest.fixture(scope="module")
def tabla_conversion():
    return construir_tabla_conversion(cargar_ingredientes())


def test_factor_harina_es_25kg_por_saco(tabla_conversion):
    assert tabla_conversion["harina"]["factor"] == 25.0


def test_factor_salsa_pelatti_es_decimal(tabla_conversion):
    # Lata 2.55 kg -> el factor no siempre es un número redondo
    assert tabla_conversion["salsa_pelatti"]["factor"] == 2.55


def test_conversion_10_sacos_harina_a_kg(tabla_conversion):
    assert formatos_a_unidad_base("harina", 10, tabla_conversion) == 250.0


def test_conversion_es_inversa(tabla_conversion):
    kg = formatos_a_unidad_base("mozzarella", 3, tabla_conversion)
    formatos = unidad_base_a_formatos("mozzarella", kg, tabla_conversion)
    assert math.isclose(formatos, 3)


def test_ingrediente_desconocido_lanza_error(tabla_conversion):
    with pytest.raises(IngredienteDesconocidoError):
        formatos_a_unidad_base("aji_chombo", 3, tabla_conversion)


def test_agregar_columna_convierte_orden_real(tabla_conversion):
    df_orden = cargar_orden()
    df = agregar_columna_unidad_base(df_orden, tabla_conversion)

    fila = df[(df["sucursal"] == "Brisas del Golf") & (df["ingrediente_id"] == "harina")]
    assert fila["cantidad_unidad_base"].iloc[0] == 250.0


def test_agregar_columna_deja_nan_en_ingrediente_desconocido(tabla_conversion):
    df_orden = cargar_orden()
    df = agregar_columna_unidad_base(df_orden, tabla_conversion)

    fila = df[(df["sucursal"] == "Costa del Este") & (df["ingrediente_id"] == "aji_chombo")]
    assert math.isnan(fila["cantidad_unidad_base"].iloc[0])
