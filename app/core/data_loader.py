"""
Carga y validación de los datos de entrada.

Este módulo es la única puerta de entrada a los 4 CSV. Nada en el resto
de la app debería leer un CSV directamente: todo pasa por acá para que
la validación de calidad de datos se haga en un solo lugar.
"""

from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"

COLUMNAS_ESPERADAS = {
    "ingredientes": {
        "ingrediente_id",
        "nombre",
        "proveedor",
        "unidad_base",
        "formato_compra",
        "unidad_base_por_formato",
        "es_perecedero",
    },
    "inventario": {"sucursal", "ingrediente_id", "stock_actual_unidad_base"},
    "orden": {"sucursal", "ingrediente_id", "cantidad_formatos"},
    "consumo": {"sucursal", "ingrediente_id", "semana", "consumo_unidad_base"},
}


@dataclass
class ReporteCalidadDatos:
    """
    Resultado de validar los 4 archivos entre sí.

    No lanza excepciones: junta los problemas encontrados para que se
    puedan mostrar como alertas de calidad de datos en el dashboard,
    en vez de tumbar la app por un ingrediente mal escrito.
    """

    ingredientes_desconocidos: list[dict] = field(default_factory=list)
    combos_faltantes_en_orden: list[dict] = field(default_factory=list)
    combos_faltantes_en_inventario: list[dict] = field(default_factory=list)
    valores_negativos: list[dict] = field(default_factory=list)

    @property
    def tiene_problemas(self) -> bool:
        return any(
            [
                self.ingredientes_desconocidos,
                self.combos_faltantes_en_inventario,
                self.valores_negativos,
            ]
        )


def _leer_csv(nombre_archivo: str, columnas_esperadas: set[str]) -> pd.DataFrame:
    ruta = DATA_DIR / nombre_archivo
    if not ruta.exists():
        raise FileNotFoundError(
            f"No se encontró {ruta}. Verificá que el CSV esté en la carpeta data/."
        )
    # utf-8-sig porque los CSV traen BOM (típico al exportar desde Excel/Sheets)
    df = pd.read_csv(ruta, encoding="utf-8-sig")
    df.columns = [c.strip() for c in df.columns]

    faltantes = columnas_esperadas - set(df.columns)
    if faltantes:
        raise ValueError(f"{nombre_archivo} no tiene las columnas esperadas: {faltantes}")

    return df


def cargar_ingredientes() -> pd.DataFrame:
    df = _leer_csv("ingredientes.csv", COLUMNAS_ESPERADAS["ingredientes"])
    df["es_perecedero"] = df["es_perecedero"].str.strip().str.lower() == "si"
    return df


def cargar_inventario() -> pd.DataFrame:
    return _leer_csv("inventario_actual.csv", COLUMNAS_ESPERADAS["inventario"])


def cargar_orden() -> pd.DataFrame:
    return _leer_csv("orden_compra_semana.csv", COLUMNAS_ESPERADAS["orden"])


def cargar_consumo_historico() -> pd.DataFrame:
    return _leer_csv("consumo_historico.csv", COLUMNAS_ESPERADAS["consumo"])


def listar_sucursales(df_inventario: pd.DataFrame) -> list[str]:
    """Sucursales válidas, derivadas de los datos (nunca hardcodeadas)."""
    return sorted(df_inventario["sucursal"].unique().tolist())


def listar_proveedores(df_ingredientes: pd.DataFrame) -> list[str]:
    return sorted(df_ingredientes["proveedor"].unique().tolist())


def validar_datos(
    df_ingredientes: pd.DataFrame,
    df_inventario: pd.DataFrame,
    df_orden: pd.DataFrame,
    df_consumo: pd.DataFrame,
) -> ReporteCalidadDatos:
    """
    Cruza los 4 dataframes y detecta inconsistencias.

    Importante: un ingrediente que falta en la ORDEN no es un error de
    datos, es justamente lo que el reto pide detectar como alerta de
    "insumo olvidado" — por eso NO se reporta acá como problema, se
    reporta como info (combos_faltantes_en_orden) para que el motor de
    alertas lo use más adelante.
    """
    catalogo = set(df_ingredientes["ingrediente_id"])
    sucursales = sorted(set(df_inventario["sucursal"]))
    reporte = ReporteCalidadDatos()

    # 1. Ingredientes referenciados que no existen en el catálogo
    for nombre_df, df in [("orden", df_orden), ("inventario", df_inventario), ("consumo", df_consumo)]:
        desconocidos = df[~df["ingrediente_id"].isin(catalogo)]
        for _, fila in desconocidos.iterrows():
            reporte.ingredientes_desconocidos.append(
                {
                    "archivo": nombre_df,
                    "sucursal": fila["sucursal"],
                    "ingrediente_id": fila["ingrediente_id"],
                }
            )

    # 2. Combos sucursal-ingrediente que faltan en la orden (posibles insumos olvidados)
    combos_esperados = {(s, i) for s in sucursales for i in catalogo}
    combos_en_orden = set(zip(df_orden["sucursal"], df_orden["ingrediente_id"]))
    for sucursal, ingrediente in sorted(combos_esperados - combos_en_orden):
        reporte.combos_faltantes_en_orden.append(
            {"sucursal": sucursal, "ingrediente_id": ingrediente}
        )

    # 3. Combos que faltan en inventario (esto sí es un problema real: sin
    #    stock actual no se puede calcular la necesidad real)
    combos_en_inventario = set(zip(df_inventario["sucursal"], df_inventario["ingrediente_id"]))
    for sucursal, ingrediente in sorted(combos_esperados - combos_en_inventario):
        reporte.combos_faltantes_en_inventario.append(
            {"sucursal": sucursal, "ingrediente_id": ingrediente}
        )

    # 4. Valores negativos (stock, consumo o cantidad pedida no deberían serlo nunca)
    negativos_inv = df_inventario[df_inventario["stock_actual_unidad_base"] < 0]
    negativos_orden = df_orden[df_orden["cantidad_formatos"] < 0]
    negativos_consumo = df_consumo[df_consumo["consumo_unidad_base"] < 0]
    for nombre_df, df in [
        ("inventario", negativos_inv),
        ("orden", negativos_orden),
        ("consumo", negativos_consumo),
    ]:
        for _, fila in df.iterrows():
            reporte.valores_negativos.append(
                {"archivo": nombre_df, "sucursal": fila["sucursal"], "ingrediente_id": fila["ingrediente_id"]}
            )

    return reporte
