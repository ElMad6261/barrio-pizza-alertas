import pandas as pd
import pytest

from app.core.alertas import calcular_necesidad_y_orden, clasificar_alertas_de_compra, generar_alertas
from app.core.data_loader import (
    cargar_consumo_historico,
    cargar_ingredientes,
    cargar_inventario,
    cargar_orden,
    validar_datos,
)
from app.core.unidades import construir_tabla_conversion
from app.models.schemas import TipoAlerta


def _tabla_conversion_sintetica():
    df_ing = pd.DataFrame(
        [
            {
                "ingrediente_id": "queso",
                "nombre": "Queso Test",
                "proveedor": "Prov",
                "unidad_base": "kg",
                "formato_compra": "Caja 10 kg",
                "unidad_base_por_formato": 10,
                "es_perecedero": True,
            }
        ]
    )
    return construir_tabla_conversion(df_ing)


# --- Tests unitarios de clasificación (datos sintéticos, casos borde controlados) ---


def test_delta_dentro_de_tolerancia_no_genera_alerta():
    # tolerancia = 10 kg (1 formato completo); un delta de 5 kg es redondeo normal
    tabla = _tabla_conversion_sintetica()
    df = pd.DataFrame(
        [{"sucursal": "Test", "ingrediente_id": "queso", "fue_pedido": True, "necesidad_real": 50.0, "delta": 5.0}]
    )
    assert clasificar_alertas_de_compra(df, tabla) == []


def test_delta_negativo_fuera_de_tolerancia_genera_riesgo_quiebre():
    tabla = _tabla_conversion_sintetica()
    df = pd.DataFrame(
        [{"sucursal": "Test", "ingrediente_id": "queso", "fue_pedido": True, "necesidad_real": 50.0, "delta": -25.0}]
    )
    alertas = clasificar_alertas_de_compra(df, tabla)
    assert len(alertas) == 1
    assert alertas[0].tipo == TipoAlerta.RIESGO_QUIEBRE
    assert alertas[0].cantidad == 25.0


def test_delta_positivo_fuera_de_tolerancia_genera_sobre_pedido():
    tabla = _tabla_conversion_sintetica()
    df = pd.DataFrame(
        [{"sucursal": "Test", "ingrediente_id": "queso", "fue_pedido": True, "necesidad_real": 20.0, "delta": 30.0}]
    )
    alertas = clasificar_alertas_de_compra(df, tabla)
    assert len(alertas) == 1
    assert alertas[0].tipo == TipoAlerta.SOBRE_PEDIDO


def test_no_pedido_con_necesidad_real_genera_insumo_olvidado():
    tabla = _tabla_conversion_sintetica()
    df = pd.DataFrame(
        [{"sucursal": "Test", "ingrediente_id": "queso", "fue_pedido": False, "necesidad_real": 40.0, "delta": -40.0}]
    )
    alertas = clasificar_alertas_de_compra(df, tabla)
    assert len(alertas) == 1
    assert alertas[0].tipo == TipoAlerta.INSUMO_OLVIDADO


def test_no_pedido_con_stock_de_sobra_no_genera_alerta_falsa():
    """
    Caso borde importante: la sucursal no pidió nada, pero como ya
    sobraba inventario, necesidad_real quedó en 0 (clip a mínimo 0).
    No debería alertar "sobre-pedido" sobre una orden que ni siquiera
    existe.
    """
    tabla = _tabla_conversion_sintetica()
    df = pd.DataFrame(
        [{"sucursal": "Test", "ingrediente_id": "queso", "fue_pedido": False, "necesidad_real": 0.0, "delta": 0.0}]
    )
    assert clasificar_alertas_de_compra(df, tabla) == []


# --- Integración contra los datos reales del reto ---


@pytest.fixture(scope="module")
def datos():
    return {
        "ingredientes": cargar_ingredientes(),
        "inventario": cargar_inventario(),
        "orden": cargar_orden(),
        "consumo": cargar_consumo_historico(),
    }


@pytest.fixture(scope="module")
def resumen_real(datos):
    reporte = validar_datos(datos["ingredientes"], datos["inventario"], datos["orden"], datos["consumo"])
    return generar_alertas(
        datos["ingredientes"], datos["inventario"], datos["orden"], datos["consumo"], reporte
    )


def test_necesidad_real_nunca_es_negativa(datos):
    df = calcular_necesidad_y_orden(
        datos["ingredientes"], datos["inventario"], datos["orden"], datos["consumo"]
    )
    assert (df["necesidad_real"] >= 0).all()


def test_resumen_real_cuenta_coincide_con_la_lista(resumen_real):
    assert resumen_real.total_alertas == len(resumen_real.alertas)
    assert resumen_real.total_alertas == (
        resumen_real.riesgo_quiebre
        + resumen_real.sobre_pedido
        + resumen_real.insumos_olvidados
        + resumen_real.ingredientes_desconocidos
    )


def test_mozzarella_brisas_del_golf_es_insumo_olvidado(resumen_real):
    # necesidad_real ~178 kg, nunca se pidió -> insumo olvidado, no riesgo_quiebre genérico
    encontrada = [
        a for a in resumen_real.alertas if a.sucursal == "Brisas del Golf" and a.ingrediente == "Mozzarella"
    ]
    assert len(encontrada) == 1
    assert encontrada[0].tipo == TipoAlerta.INSUMO_OLVIDADO
    assert encontrada[0].cantidad == pytest.approx(178.1, abs=0.5)


def test_cebolla_brisas_del_golf_es_sobre_pedido(resumen_real):
    # necesidad_real ~29 kg, pidieron 100 kg -> ~71 kg de más
    encontrada = [
        a for a in resumen_real.alertas if a.sucursal == "Brisas del Golf" and a.ingrediente == "Cebolla blanca"
    ]
    assert len(encontrada) == 1
    assert encontrada[0].tipo == TipoAlerta.SOBRE_PEDIDO
    assert encontrada[0].cantidad == pytest.approx(71.0, abs=0.5)


def test_harina_costa_del_este_es_riesgo_quiebre(resumen_real):
    # con tendencia de crecimiento proyectada (~330 kg), pidieron solo ~180 kg
    encontrada = [
        a for a in resumen_real.alertas if a.sucursal == "Costa del Este" and a.ingrediente == "Harina 00"
    ]
    assert len(encontrada) == 1
    assert encontrada[0].tipo == TipoAlerta.RIESGO_QUIEBRE
    assert encontrada[0].cantidad == pytest.approx(150.3, abs=0.5)


def test_albahaca_via_argentina_es_sobre_pedido(resumen_real):
    encontrada = [
        a for a in resumen_real.alertas if a.sucursal == "Via Argentina" and a.ingrediente == "Albahaca fresca"
    ]
    assert len(encontrada) == 1
    assert encontrada[0].tipo == TipoAlerta.SOBRE_PEDIDO


def test_ingrediente_desconocido_si_genera_alerta_visible(resumen_real):
    # A diferencia de una versión anterior de este motor: aji_chombo NO
    # se descarta silenciosamente. No se puede convertir a unidad base
    # (no está en el catálogo), pero sí se muestra como alerta de
    # calidad de datos, para que la gerente de compras no se quede sin
    # saber que esa línea de la orden nunca se validó.
    coincidencias = [a for a in resumen_real.alertas if a.tipo == TipoAlerta.INGREDIENTE_DESCONOCIDO]
    assert len(coincidencias) == 1
    assert coincidencias[0].sucursal == "Costa del Este"
    assert "chombo" in coincidencias[0].ingrediente.lower()


def test_todas_las_alertas_tienen_mensaje_con_formato_alerta(resumen_real):
    for a in resumen_real.alertas:
        assert a.mensaje.startswith("ALERTA:")


def test_no_hay_alertas_duplicadas_por_combo(resumen_real):
    combos = [(a.sucursal, a.ingrediente, a.tipo) for a in resumen_real.alertas]
    assert len(combos) == len(set(combos))


def test_resumen_real_ordenado_por_cantidad_descendente(resumen_real):
    cantidades = [a.cantidad for a in resumen_real.alertas]
    assert cantidades == sorted(cantidades, reverse=True)


def test_generar_alertas_no_rompe_con_datos_reales_completos(resumen_real):
    assert resumen_real.total_alertas > 0
    tipos_validos = {t for t in TipoAlerta}
    assert all(a.tipo in tipos_validos for a in resumen_real.alertas)
