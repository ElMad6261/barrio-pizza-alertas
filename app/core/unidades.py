"""
Conversión entre "formatos de compra" (como vienen en la orden semanal)
y "unidad base" (como vienen el inventario y el consumo histórico).

Ejemplo: harina se compra en "Saco 25 kg" → unidad_base_por_formato = 25.
Si una sucursal pide 10 sacos, en unidad base son 250 kg.
"""

import pandas as pd


class IngredienteDesconocidoError(Exception):
    """Se pidió convertir un ingrediente que no está en el catálogo."""


def construir_tabla_conversion(df_ingredientes: pd.DataFrame) -> dict[str, dict]:
    """
    Devuelve un dict indexado por ingrediente_id con la info necesaria
    para convertir y para armar mensajes de alerta legibles:

        {
            "harina": {
                "nombre": "Harina 00",
                "unidad_base": "kg",
                "formato_compra": "Saco 25 kg",
                "factor": 25.0,
                "proveedor": "Molinos Central",
                "es_perecedero": False,
            },
            ...
        }
    """
    tabla = {}
    for _, fila in df_ingredientes.iterrows():
        tabla[fila["ingrediente_id"]] = {
            "nombre": fila["nombre"],
            "unidad_base": fila["unidad_base"],
            "formato_compra": fila["formato_compra"],
            "factor": float(fila["unidad_base_por_formato"]),
            "proveedor": fila["proveedor"],
            "es_perecedero": bool(fila["es_perecedero"]),
        }
    return tabla


def formatos_a_unidad_base(
    ingrediente_id: str, cantidad_formatos: float, tabla_conversion: dict[str, dict]
) -> float:
    """Convierte una cantidad en formatos (ej. 10 sacos) a unidad base (ej. 250 kg)."""
    if ingrediente_id not in tabla_conversion:
        raise IngredienteDesconocidoError(
            f"'{ingrediente_id}' no está en el catálogo de ingredientes."
        )
    return cantidad_formatos * tabla_conversion[ingrediente_id]["factor"]


def unidad_base_a_formatos(
    ingrediente_id: str, cantidad_unidad_base: float, tabla_conversion: dict[str, dict]
) -> float:
    """Inverso de formatos_a_unidad_base. Útil para expresar un déficit/exceso en formatos."""
    if ingrediente_id not in tabla_conversion:
        raise IngredienteDesconocidoError(
            f"'{ingrediente_id}' no está en el catálogo de ingredientes."
        )
    factor = tabla_conversion[ingrediente_id]["factor"]
    return cantidad_unidad_base / factor


def agregar_columna_unidad_base(
    df_orden: pd.DataFrame, tabla_conversion: dict[str, dict]
) -> pd.DataFrame:
    """
    Devuelve una copia de df_orden con una columna nueva
    'cantidad_unidad_base', ya convertida.

    Las filas cuyo ingrediente no está en el catálogo quedan con NaN
    en vez de romper todo el cálculo — el reporte de calidad de datos
    (data_loader.validar_datos) ya las señala por separado.
    """
    df = df_orden.copy()

    def _convertir(fila):
        try:
            return formatos_a_unidad_base(
                fila["ingrediente_id"], fila["cantidad_formatos"], tabla_conversion
            )
        except IngredienteDesconocidoError:
            return float("nan")

    df["cantidad_unidad_base"] = df.apply(_convertir, axis=1)
    return df
