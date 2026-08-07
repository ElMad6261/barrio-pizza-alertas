import numpy as np
import pytest

from app.core.data_loader import cargar_consumo_historico
from app.core.proyeccion import (
    MIN_PUNTOS_PARA_TENDENCIA,
    detectar_outliers,
    proyectar_consumo,
    proyectar_todas_las_combinaciones,
)
from app.models.schemas import MetodoProyeccion


def test_detecta_pico_real_pepperoni_marbella():
    # Serie real: Marbella, pepperoni -> semana 3 con un pico claro
    valores = np.array([28.0, 30.0, 150.0, 27.0, 29.0, 31.0])
    outliers = detectar_outliers(valores)
    assert outliers.tolist() == [False, False, True, False, False, False]


def test_serie_practicamente_constante_no_marca_outliers():
    # Serie real: Via Argentina, albahaca -> variación mínima, no debería marcar nada
    valores = np.array([1.5, 1.5, 1.0, 1.5, 1.5, 1.5])
    outliers = detectar_outliers(valores)
    assert not outliers.any()


def test_serie_sin_variacion_no_rompe():
    valores = np.array([10.0, 10.0, 10.0, 10.0, 10.0, 10.0])
    outliers = detectar_outliers(valores)
    assert not outliers.any()


def test_proyeccion_detecta_tendencia_real_harina_costa_del_este():
    # Serie real: crecimiento limpio, R2 = 1.0
    semanas = [1, 2, 3, 4, 5, 6]
    valores = [240.0, 255.0, 268.0, 284.0, 300.0, 316.0]
    resultado = proyectar_consumo(semanas, valores)

    assert resultado.metodo == MetodoProyeccion.TENDENCIA
    assert resultado.r2 > 0.95
    # La tendencia sugiere ~15-16 kg más que la última semana (316)
    assert 325 < resultado.valor_proyectado < 340


def test_proyeccion_excluye_outlier_y_no_se_deja_arrastrar_por_el_pico():
    semanas = [1, 2, 3, 4, 5, 6]
    valores = [28.0, 30.0, 150.0, 27.0, 29.0, 31.0]
    resultado = proyectar_consumo(semanas, valores)

    assert 3 in resultado.semanas_excluidas
    # Un promedio simple sin filtrar daría ~49; con el outlier excluido
    # el resultado debe quedarse cerca del rango normal de la serie (27-31)
    assert resultado.valor_proyectado < 40


def test_proyeccion_serie_plana_usa_promedio_ponderado():
    semanas = [1, 2, 3, 4, 5, 6]
    valores = [12.0, 13.0, 14.0, 13.0, 12.0, 13.0]  # sin tendencia clara
    resultado = proyectar_consumo(semanas, valores)

    assert resultado.metodo == MetodoProyeccion.PROMEDIO_PONDERADO


def test_proyeccion_nunca_da_valores_negativos():
    semanas = [1, 2, 3, 4, 5, 6]
    valores = [10.0, 8.0, 6.0, 4.0, 2.0, 0.5]  # tendencia decreciente fuerte
    resultado = proyectar_consumo(semanas, valores)
    assert resultado.valor_proyectado >= 0.0


def test_r2_nunca_es_negative_zero():
    # Caso real: Marbella/aceite_oliva da un r2 negativo minúsculo que
    # redondeado quedaba en -0.0 en vez de 0.0.
    semanas = [1, 2, 3, 4, 5, 6]
    valores = [20.0, 21.0, 19.0, 22.0, 20.0, 21.0]
    resultado = proyectar_consumo(semanas, valores)
    if resultado.r2 is not None:
        assert str(resultado.r2) != "-0.0"


def test_proyectar_todas_las_combinaciones_cubre_los_88_combos():
    df_consumo = cargar_consumo_historico()
    resultado = proyectar_todas_las_combinaciones(df_consumo)

    assert len(resultado) == 4 * 22
    assert resultado["consumo_proyectado"].isnull().sum() == 0
    assert (resultado["consumo_proyectado"] >= 0).all()
    assert set(resultado["metodo"].unique()) <= {m.value for m in MetodoProyeccion}


def test_proyectar_todas_las_combinaciones_marca_pepperoni_marbella_con_outlier():
    df_consumo = cargar_consumo_historico()
    resultado = proyectar_todas_las_combinaciones(df_consumo)

    fila = resultado[
        (resultado["sucursal"] == "Marbella") & (resultado["ingrediente_id"] == "pepperoni")
    ].iloc[0]
    assert 3 in fila["semanas_excluidas"]
