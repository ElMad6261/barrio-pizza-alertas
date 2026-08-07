"""
Motor de alertas de compras.

Junta proyección de consumo, inventario actual y orden de compra para
generar las alertas finales que va a mostrar el dashboard.

Reglas:
- necesidad_real = proyección de consumo − inventario actual, acotada
  a un mínimo de 0: si ya sobra inventario, la necesidad real es 0, no
  un número negativo. Esto importa para el caso de una sucursal con
  stock de sobra que directamente no pide nada — necesidad_real
  negativa haría que ese "pedido vacío" se viera como una diferencia
  grande contra un negativo, y se marcaría sobre-pedido sobre una
  orden que ni siquiera existe. Con el clip en 0, pedido=0 y
  necesidad=0 dan delta=0: correctamente, sin alerta.
- Un insumo que no aparece en la orden de una sucursal, pero tiene una
  necesidad real por encima de la tolerancia, se marca como "insumo
  olvidado" en vez de mezclarse con un riesgo de quiebre genérico —
  la causa raíz es distinta (nunca se pidió, vs. se pidió de menos) y
  el reto pide poder distinguir ambos casos.
- Solo se compran formatos completos: una diferencia menor a UN formato
  completo del ingrediente se considera redondeo normal, no una alerta.
- Los ingredientes que aparecen en la orden pero no existen en el
  catálogo (ver data_loader.validar_datos) quedan fuera del cálculo de
  necesidad/delta —no hay forma de convertirlos a unidad base— pero sí
  generan su propia alerta de calidad de datos, para que no desaparezcan
  silenciosamente del dashboard.
"""

import pandas as pd

from app.core.data_loader import ReporteCalidadDatos
from app.core.proyeccion import proyectar_todas_las_combinaciones
from app.core.unidades import (
    agregar_columna_unidad_base,
    construir_tabla_conversion,
    unidad_base_a_formatos,
)
from app.models.schemas import Alerta, ResumenSemanal, TipoAlerta

TOLERANCIA_FORMATOS = 1.0  # formatos completos de tolerancia antes de alertar


def _redondear(valor: float, decimales: int = 1) -> float:
    return round(float(valor), decimales)


def _mensaje_riesgo_quiebre(sucursal: str, nombre: str, unidad: str, faltante: float, formatos_aprox: float) -> str:
    return (
        f"ALERTA: {sucursal} está pidiendo {_redondear(faltante)} {unidad} de {nombre} "
        f"menos que lo proyectado (~{formatos_aprox} formato(s) de menos) → riesgo de quiebre."
    )


def _mensaje_sobre_pedido(sucursal: str, nombre: str, unidad: str, excedente: float, formatos_aprox: float) -> str:
    return (
        f"ALERTA: {sucursal} está pidiendo {_redondear(excedente)} {unidad} de {nombre} "
        f"más que lo proyectado (~{formatos_aprox} formato(s) de más) → capital inmovilizado "
        f"en stock que puede vencerse."
    )


def _mensaje_insumo_olvidado(sucursal: str, nombre: str, unidad: str, necesidad: float) -> str:
    return (
        f"ALERTA: {sucursal} no incluyó {nombre} en su orden de esta semana, pero se "
        f"proyecta una necesidad de {_redondear(necesidad)} {unidad} → riesgo de quiebre."
    )


def _mensaje_ingrediente_desconocido(sucursal: str, ingrediente_id: str) -> str:
    return (
        f"ALERTA: {sucursal} pidió '{ingrediente_id}', que no está en el catálogo de "
        f"ingredientes → no se pudo validar ni convertir esta línea."
    )


def calcular_necesidad_y_orden(
    df_ingredientes: pd.DataFrame,
    df_inventario: pd.DataFrame,
    df_orden: pd.DataFrame,
    df_consumo: pd.DataFrame,
) -> pd.DataFrame:
    """
    Arma una tabla con una fila por sucursal-ingrediente (de las 88
    combinaciones del catálogo), con todo lo necesario para decidir
    qué alerta —si alguna— corresponde: proyección, inventario,
    necesidad real, cantidad pedida y el delta entre lo pedido y lo
    necesario.
    """
    tabla_conversion = construir_tabla_conversion(df_ingredientes)

    df_proy = proyectar_todas_las_combinaciones(df_consumo)

    df_inv = df_inventario.rename(columns={"stock_actual_unidad_base": "inventario_actual"})
    df = df_proy.merge(
        df_inv[["sucursal", "ingrediente_id", "inventario_actual"]],
        on=["sucursal", "ingrediente_id"],
        how="left",
    )

    df["necesidad_real_bruta"] = df["consumo_proyectado"] - df["inventario_actual"]
    df["necesidad_real"] = df["necesidad_real_bruta"].clip(lower=0)

    df_orden_conv = agregar_columna_unidad_base(df_orden, tabla_conversion)
    df_orden_valida = df_orden_conv.dropna(subset=["cantidad_unidad_base"])

    df = df.merge(
        df_orden_valida[["sucursal", "ingrediente_id", "cantidad_unidad_base"]],
        on=["sucursal", "ingrediente_id"],
        how="left",
    )
    df["fue_pedido"] = df["cantidad_unidad_base"].notna()
    df["cantidad_pedida"] = df["cantidad_unidad_base"].fillna(0.0)
    df["delta"] = df["cantidad_pedida"] - df["necesidad_real"]

    return df


def clasificar_alertas_de_compra(
    df: pd.DataFrame, tabla_conversion: dict[str, dict]
) -> list[Alerta]:
    """Aplica la tolerancia de redondeo y clasifica cada fila en un tipo de alerta (o ninguno)."""
    alertas: list[Alerta] = []

    for _, fila in df.iterrows():
        info = tabla_conversion[fila["ingrediente_id"]]
        tolerancia = info["factor"] * TOLERANCIA_FORMATOS
        unidad = info["unidad_base"]
        nombre = info["nombre"]
        sucursal = fila["sucursal"]

        if not fila["fue_pedido"] and fila["necesidad_real"] > tolerancia:
            alertas.append(
                Alerta(
                    sucursal=sucursal,
                    ingrediente=nombre,
                    tipo=TipoAlerta.INSUMO_OLVIDADO,
                    cantidad=_redondear(fila["necesidad_real"]),
                    unidad=unidad,
                    mensaje=_mensaje_insumo_olvidado(sucursal, nombre, unidad, fila["necesidad_real"]),
                )
            )
            continue

        delta = fila["delta"]

        if delta < -tolerancia:
            faltante = abs(delta)
            formatos_aprox = round(
                unidad_base_a_formatos(fila["ingrediente_id"], faltante, tabla_conversion), 1
            )
            alertas.append(
                Alerta(
                    sucursal=sucursal,
                    ingrediente=nombre,
                    tipo=TipoAlerta.RIESGO_QUIEBRE,
                    cantidad=_redondear(faltante),
                    unidad=unidad,
                    mensaje=_mensaje_riesgo_quiebre(sucursal, nombre, unidad, faltante, formatos_aprox),
                )
            )
        elif delta > tolerancia:
            formatos_aprox = round(
                unidad_base_a_formatos(fila["ingrediente_id"], delta, tabla_conversion), 1
            )
            alertas.append(
                Alerta(
                    sucursal=sucursal,
                    ingrediente=nombre,
                    tipo=TipoAlerta.SOBRE_PEDIDO,
                    cantidad=_redondear(delta),
                    unidad=unidad,
                    mensaje=_mensaje_sobre_pedido(sucursal, nombre, unidad, delta, formatos_aprox),
                )
            )
        # else: dentro de tolerancia de redondeo -> no se genera alerta

    return alertas


def generar_alertas_calidad_datos(
    reporte: ReporteCalidadDatos, df_orden: pd.DataFrame
) -> list[Alerta]:
    """
    Convierte los ingredientes desconocidos detectados en la orden
    (data_loader.validar_datos) en alertas visibles en el dashboard,
    en vez de dejarlos solo en un reporte que nadie ve.
    """
    alertas = []
    for item in reporte.ingredientes_desconocidos:
        if item["archivo"] != "orden":
            continue
        fila_orden = df_orden[
            (df_orden["sucursal"] == item["sucursal"])
            & (df_orden["ingrediente_id"] == item["ingrediente_id"])
        ].iloc[0]
        alertas.append(
            Alerta(
                sucursal=item["sucursal"],
                ingrediente=item["ingrediente_id"],
                tipo=TipoAlerta.INGREDIENTE_DESCONOCIDO,
                cantidad=float(fila_orden["cantidad_formatos"]),
                unidad="formatos (sin catálogo)",
                mensaje=_mensaje_ingrediente_desconocido(item["sucursal"], item["ingrediente_id"]),
            )
        )
    return alertas


def construir_resumen_proyecciones(df: pd.DataFrame, tabla_conversion: dict[str, dict]) -> list[dict]:
    """
    A partir del DataFrame de calcular_necesidad_y_orden (que ya trae
    consumo_proyectado, metodo, r2 y semanas_excluidas de la etapa de
    proyección), arma las filas listas para ProyeccionResumen — sin el
    histórico, para mantener liviana la respuesta de la tabla completa.
    """
    filas = []
    for _, fila in df.iterrows():
        info = tabla_conversion[fila["ingrediente_id"]]
        filas.append(
            {
                "sucursal": fila["sucursal"],
                "ingrediente": info["nombre"],
                "ingrediente_id": fila["ingrediente_id"],
                "consumo_proyectado": round(fila["consumo_proyectado"], 1),
                "inventario_actual": round(fila["inventario_actual"], 1),
                "necesidad_real": round(fila["necesidad_real"], 1),
                "cantidad_pedida": round(fila["cantidad_pedida"], 1),
                "unidad": info["unidad_base"],
                "metodo": fila["metodo"],
                "r2": fila["r2"] if pd.notna(fila["r2"]) else None,
                "semanas_excluidas": fila["semanas_excluidas"],
                "delta_vs_pedido": round(fila["cantidad_pedida"] - fila["necesidad_real"], 1),
            }
        )
    return filas


def generar_alertas(
    df_ingredientes: pd.DataFrame,
    df_inventario: pd.DataFrame,
    df_orden: pd.DataFrame,
    df_consumo: pd.DataFrame,
    reporte_calidad: ReporteCalidadDatos,
) -> ResumenSemanal:
    """Orquesta todo el pipeline y arma el resumen que consume la API."""
    tabla_conversion = construir_tabla_conversion(df_ingredientes)
    df = calcular_necesidad_y_orden(df_ingredientes, df_inventario, df_orden, df_consumo)

    alertas = clasificar_alertas_de_compra(df, tabla_conversion)
    alertas += generar_alertas_calidad_datos(reporte_calidad, df_orden)

    # De un vistazo, lo más urgente primero.
    alertas.sort(key=lambda a: a.cantidad, reverse=True)

    return ResumenSemanal(
        total_alertas=len(alertas),
        riesgo_quiebre=sum(1 for a in alertas if a.tipo == TipoAlerta.RIESGO_QUIEBRE),
        sobre_pedido=sum(1 for a in alertas if a.tipo == TipoAlerta.SOBRE_PEDIDO),
        insumos_olvidados=sum(1 for a in alertas if a.tipo == TipoAlerta.INSUMO_OLVIDADO),
        ingredientes_desconocidos=sum(
            1 for a in alertas if a.tipo == TipoAlerta.INGREDIENTE_DESCONOCIDO
        ),
        alertas=alertas,
    )
