import pandas as pd
import pytest

from app.core.alertas import calcular_necesidad_y_orden
from app.core.data_loader import cargar_consumo_historico, cargar_ingredientes, cargar_inventario, cargar_orden
from app.core.pedido_corregido import agrupar_por_proveedor, calcular_pedido_corregido
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
def tabla_conversion(datos):
    return construir_tabla_conversion(datos["ingredientes"])


@pytest.fixture(scope="module")
def pedido_por_proveedor(datos, tabla_conversion):
    df_necesidad = calcular_necesidad_y_orden(
        datos["ingredientes"], datos["inventario"], datos["orden"], datos["consumo"]
    )
    df_pedido = calcular_pedido_corregido(df_necesidad, tabla_conversion)
    return agrupar_por_proveedor(df_pedido)


def test_redondea_hacia_arriba_al_formato_completo():
    # necesidad de 26 kg con formato de 25 kg -> 2 sacos, no 1.04
    tabla = construir_tabla_conversion(
        pd.DataFrame(
            [
                {
                    "ingrediente_id": "harina",
                    "nombre": "Harina",
                    "proveedor": "Molinos",
                    "unidad_base": "kg",
                    "formato_compra": "Saco 25 kg",
                    "unidad_base_por_formato": 25,
                    "es_perecedero": False,
                }
            ]
        )
    )
    df = pd.DataFrame(
        [
            {
                "sucursal": "Test",
                "ingrediente_id": "harina",
                "necesidad_real": 26.0,
                "cantidad_pedida": 0.0,
                "fue_pedido": False,
            }
        ]
    )
    resultado = calcular_pedido_corregido(df, tabla)
    assert resultado.iloc[0]["cantidad_formatos_corregida"] == 2.0


def test_necesidad_cero_no_genera_linea_de_pedido():
    tabla = construir_tabla_conversion(
        pd.DataFrame(
            [
                {
                    "ingrediente_id": "harina",
                    "nombre": "Harina",
                    "proveedor": "Molinos",
                    "unidad_base": "kg",
                    "formato_compra": "Saco 25 kg",
                    "unidad_base_por_formato": 25,
                    "es_perecedero": False,
                }
            ]
        )
    )
    df = pd.DataFrame(
        [
            {
                "sucursal": "Test",
                "ingrediente_id": "harina",
                "necesidad_real": 0.0,
                "cantidad_pedida": 250.0,  # pidieron de más, pero no se necesitaba nada
                "fue_pedido": True,
            }
        ]
    )
    df_pedido = calcular_pedido_corregido(df, tabla)
    agrupado = agrupar_por_proveedor(df_pedido)
    assert agrupado == []  # ningún proveedor recibe una línea en 0


def test_agrupa_los_8_proveedores_reales(pedido_por_proveedor):
    proveedores = {p.proveedor for p in pedido_por_proveedor}
    # No todos los proveedores necesariamente tienen líneas > 0 esta semana,
    # pero el set de proveedores presentes debe ser subconjunto de los 8 reales.
    proveedores_reales = {
        "AgroFresco",
        "Deli Gourmet",
        "Distrib. Bella Italia",
        "EmpaqueTodo",
        "Hongos del Valle",
        "Importadora Istmo",
        "Molinos Central",
        "Verduras La Huerta",
    }
    assert proveedores <= proveedores_reales
    assert len(proveedores) > 0


def test_cada_linea_indica_si_hubo_cambio(pedido_por_proveedor):
    for proveedor in pedido_por_proveedor:
        for linea in proveedor.lineas:
            cambio_esperado = linea.cantidad_formatos_original != linea.cantidad_formatos_corregida
            assert linea.cambio == cambio_esperado


def test_total_lineas_corregidas_coincide_con_el_conteo_real(pedido_por_proveedor):
    for proveedor in pedido_por_proveedor:
        cambios_reales = sum(1 for l in proveedor.lineas if l.cambio)
        assert proveedor.total_lineas_corregidas == cambios_reales


def test_proveedores_ordenados_alfabeticamente(pedido_por_proveedor):
    nombres = [p.proveedor for p in pedido_por_proveedor]
    assert nombres == sorted(nombres)
