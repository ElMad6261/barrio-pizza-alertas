"""
Pedido corregido, agrupado por proveedor.

Cada proveedor recibe su propia orden (harina y semola van a Molinos
Central, mozzarella y burrata van a Distrib. Bella Italia, etc.), así
que agrupar por proveedor es lo que permite reenviarle a cada uno
directamente la parte que le corresponde, ya corregida.

La cantidad corregida se calcula redondeando la necesidad real HACIA
ARRIBA al formato completo más cercano (no se puede comprar medio
saco). Una línea con necesidad real de 0 no entra en el pedido
corregido — no tiene sentido reenviarle al proveedor una línea en 0.
"""

import math

import pandas as pd

from app.models.schemas import LineaPedidoCorregido, PedidoPorProveedor


def calcular_pedido_corregido(
    df_necesidad_y_orden: pd.DataFrame, tabla_conversion: dict[str, dict]
) -> pd.DataFrame:
    """
    df_necesidad_y_orden: la tabla que arma
    alertas.calcular_necesidad_y_orden (necesidad_real, cantidad_pedida
    en unidad base, fue_pedido).
    """
    filas = []
    for _, fila in df_necesidad_y_orden.iterrows():
        info = tabla_conversion[fila["ingrediente_id"]]
        factor = info["factor"]

        cantidad_formatos_original = (fila["cantidad_pedida"] / factor) if fila["fue_pedido"] else 0.0
        cantidad_formatos_corregida = (
            math.ceil(fila["necesidad_real"] / factor) if fila["necesidad_real"] > 0 else 0.0
        )

        filas.append(
            {
                "sucursal": fila["sucursal"],
                "ingrediente_id": fila["ingrediente_id"],
                "proveedor": info["proveedor"],
                "nombre": info["nombre"],
                "formato_compra": info["formato_compra"],
                "unidad_base": info["unidad_base"],
                "cantidad_formatos_original": round(cantidad_formatos_original, 1),
                "cantidad_formatos_corregida": float(cantidad_formatos_corregida),
            }
        )

    return pd.DataFrame(filas)


def agrupar_por_proveedor(df_pedido_corregido: pd.DataFrame) -> list[PedidoPorProveedor]:
    """Agrupa el pedido corregido por proveedor, listo para reenviar a cada uno."""
    resultado = []

    for proveedor, grupo in df_pedido_corregido.groupby("proveedor"):
        grupo_relevante = grupo[grupo["cantidad_formatos_corregida"] > 0].copy()
        if grupo_relevante.empty:
            continue

        lineas = [
            LineaPedidoCorregido(
                sucursal=fila["sucursal"],
                ingrediente=fila["nombre"],
                formato_compra=fila["formato_compra"],
                unidad_base=fila["unidad_base"],
                cantidad_formatos_original=fila["cantidad_formatos_original"],
                cantidad_formatos_corregida=fila["cantidad_formatos_corregida"],
                cambio=fila["cantidad_formatos_original"] != fila["cantidad_formatos_corregida"],
            )
            for _, fila in grupo_relevante.sort_values(["sucursal", "nombre"]).iterrows()
        ]

        resultado.append(
            PedidoPorProveedor(
                proveedor=proveedor,
                lineas=lineas,
                total_lineas_corregidas=sum(1 for l in lineas if l.cambio),
            )
        )

    resultado.sort(key=lambda p: p.proveedor)
    return resultado
