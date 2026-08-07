"""
Motor de proyección de consumo semanal.

Para cada combinación sucursal-ingrediente, proyecta el consumo de la
próxima semana a partir de las últimas 6 semanas de histórico.

Estrategia:
1. Detecta semanas atípicas DENTRO de la propia serie (con z-score
   modificado, basado en MAD) y las excluye antes de proyectar — una
   sola semana rara (ej. un evento puntual, un error de carga) no
   debería distorsionar la proyección de las demás semanas.
2. Si con los puntos restantes se puede ajustar una recta con
   confianza razonable (R² >= umbral), se usa esa tendencia para
   proyectar la semana que viene.
3. Si no hay señal de tendencia clara, se usa un promedio ponderado
   que le da más peso a las semanas más recientes.
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd

from app.models.schemas import MetodoProyeccion

UMBRAL_MODIFIED_ZSCORE = 3.5
UMBRAL_R2_TENDENCIA = 0.5
MIN_PUNTOS_PARA_TENDENCIA = 4


@dataclass
class ResultadoProyeccion:
    valor_proyectado: float
    metodo: MetodoProyeccion
    r2: float | None
    semanas_excluidas: list[int]


def detectar_outliers(valores: np.ndarray, umbral: float = UMBRAL_MODIFIED_ZSCORE) -> np.ndarray:
    """
    Devuelve un array booleano: True donde el valor es atípico dentro
    de su propia serie, usando el z-score modificado (basado en MAD:
    desviación absoluta respecto a la mediana). Es más robusto que el
    desvío estándar clásico para series cortas de 6 puntos, porque un
    solo valor extremo no infla la propia medida de dispersión.

    Si la serie es prácticamente constante (MAD = 0), no se marca
    ningún punto como atípico: con tan poca variación no hay forma
    confiable de distinguir ruido normal de un valor realmente raro.
    """
    mediana = np.median(valores)
    mad = np.median(np.abs(valores - mediana))
    if mad == 0:
        return np.zeros(len(valores), dtype=bool)
    z_modificado = 0.6745 * (valores - mediana) / mad
    return np.abs(z_modificado) > umbral


def _promedio_ponderado(semanas: np.ndarray, valores: np.ndarray) -> float:
    """Promedio ponderado dando más peso a las semanas más recientes."""
    pesos = semanas.astype(float)  # la semana 6 pesa más que la semana 1
    return float(np.average(valores, weights=pesos))


def _redondear_r2(r2: float) -> float:
    # round() puede devolver -0.0 cuando r2 es un negativo minúsculo
    # (peor que la media, pero por muy poco) — se normaliza a 0.0 para
    # que el frontend no reciba un signo negativo sin sentido visual.
    return round(r2, 3) + 0.0


def proyectar_consumo(semanas: list[int], valores: list[float]) -> ResultadoProyeccion:
    """
    semanas: números de semana, ej. [1, 2, 3, 4, 5, 6]
    valores: consumo de cada semana, en el mismo orden que `semanas`
    """
    semanas_arr = np.array(semanas)
    valores_arr = np.array(valores, dtype=float)

    orden = np.argsort(semanas_arr)
    semanas_arr, valores_arr = semanas_arr[orden], valores_arr[orden]

    es_outlier = detectar_outliers(valores_arr)
    semanas_excluidas = semanas_arr[es_outlier].tolist()

    semanas_filtradas = semanas_arr[~es_outlier]
    valores_filtrados = valores_arr[~es_outlier]

    # Salvavidas: si por algún motivo se excluyó todo, no nos quedamos
    # sin datos para proyectar — se usa la serie completa sin filtrar.
    if len(semanas_filtradas) == 0:
        semanas_filtradas, valores_filtrados = semanas_arr, valores_arr
        semanas_excluidas = []

    siguiente_semana = int(semanas_arr.max()) + 1
    r2 = None

    if len(semanas_filtradas) >= MIN_PUNTOS_PARA_TENDENCIA:
        pendiente, intercepto = np.polyfit(semanas_filtradas, valores_filtrados, 1)
        prediccion = pendiente * semanas_filtradas + intercepto
        ss_res = np.sum((valores_filtrados - prediccion) ** 2)
        ss_tot = np.sum((valores_filtrados - valores_filtrados.mean()) ** 2)
        r2 = float(1 - ss_res / ss_tot) if ss_tot > 0 else 0.0

        if r2 >= UMBRAL_R2_TENDENCIA:
            valor_proyectado = pendiente * siguiente_semana + intercepto
            return ResultadoProyeccion(
                valor_proyectado=max(0.0, float(valor_proyectado)),
                metodo=MetodoProyeccion.TENDENCIA,
                r2=_redondear_r2(r2),
                semanas_excluidas=semanas_excluidas,
            )

    valor_proyectado = _promedio_ponderado(semanas_filtradas, valores_filtrados)
    return ResultadoProyeccion(
        valor_proyectado=max(0.0, valor_proyectado),
        metodo=MetodoProyeccion.PROMEDIO_PONDERADO,
        r2=_redondear_r2(r2) if r2 is not None else None,
        semanas_excluidas=semanas_excluidas,
    )


def proyectar_todas_las_combinaciones(df_consumo: pd.DataFrame) -> pd.DataFrame:
    """
    Corre proyectar_consumo() para cada combinación sucursal-ingrediente
    presente en el histórico. Devuelve un DataFrame listo para cruzar
    con inventario y con la orden de compra en el siguiente paso.
    """
    df = df_consumo.copy()
    df["semana_num"] = df["semana"].str.replace("S", "", regex=False).astype(int)

    filas = []
    for (sucursal, ingrediente_id), grupo in df.groupby(["sucursal", "ingrediente_id"]):
        grupo_ordenado = grupo.sort_values("semana_num")
        resultado = proyectar_consumo(
            grupo_ordenado["semana_num"].tolist(),
            grupo_ordenado["consumo_unidad_base"].tolist(),
        )
        filas.append(
            {
                "sucursal": sucursal,
                "ingrediente_id": ingrediente_id,
                "consumo_proyectado": resultado.valor_proyectado,
                "metodo": resultado.metodo.value,
                "r2": resultado.r2,
                "semanas_excluidas": resultado.semanas_excluidas,
            }
        )

    return pd.DataFrame(filas)
