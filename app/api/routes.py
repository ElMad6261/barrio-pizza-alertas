"""
Endpoints de la API.

Todos los endpoints leen los CSV de data/ en cada llamada. Para el
volumen de datos del reto (4 sucursales, 22 ingredientes) esto es
instantáneo; si en el futuro esto crece o se conecta a un ERP como
Odoo, este es el punto donde se cambiaría por una lectura cacheada o
por una llamada al API del ERP en vez de a los CSV.
"""

from fastapi import APIRouter, HTTPException

from app.core.alertas import calcular_necesidad_y_orden, generar_alertas
from app.core.data_loader import (
    cargar_consumo_historico,
    cargar_ingredientes,
    cargar_inventario,
    cargar_orden,
    validar_datos,
)
from app.core.pedido_corregido import agrupar_por_proveedor, calcular_pedido_corregido
from app.core.proyeccion import proyectar_consumo
from app.core.unidades import construir_tabla_conversion
from app.models.schemas import PedidoPorProveedor, ProyeccionDetalle, ResumenSemanal

router = APIRouter()


def _cargar_todo():
    df_ingredientes = cargar_ingredientes()
    df_inventario = cargar_inventario()
    df_orden = cargar_orden()
    df_consumo = cargar_consumo_historico()
    return df_ingredientes, df_inventario, df_orden, df_consumo


@router.get("/health")
def health_check():
    """Chequeo simple de que la API está viva."""
    return {"status": "ok"}


@router.get("/alertas", response_model=ResumenSemanal)
def obtener_alertas():
    """Devuelve todas las alertas de la semana actual, ordenadas por urgencia."""
    df_ingredientes, df_inventario, df_orden, df_consumo = _cargar_todo()
    reporte_calidad = validar_datos(df_ingredientes, df_inventario, df_orden, df_consumo)
    return generar_alertas(df_ingredientes, df_inventario, df_orden, df_consumo, reporte_calidad)


@router.get("/alertas/{sucursal}", response_model=list)
def obtener_alertas_por_sucursal(sucursal: str):
    """Devuelve solo las alertas de una sucursal puntual."""
    df_ingredientes, df_inventario, df_orden, df_consumo = _cargar_todo()
    reporte_calidad = validar_datos(df_ingredientes, df_inventario, df_orden, df_consumo)
    resumen = generar_alertas(df_ingredientes, df_inventario, df_orden, df_consumo, reporte_calidad)
    return [a for a in resumen.alertas if a.sucursal == sucursal]


@router.get("/pedido-corregido-por-proveedor", response_model=list[PedidoPorProveedor])
def obtener_pedido_corregido_por_proveedor():
    """
    Devuelve la orden de compra corregida (redondeada a formatos
    completos según la necesidad real), agrupada por proveedor, lista
    para reenviarle a cada uno su parte directamente.
    """
    df_ingredientes, df_inventario, df_orden, df_consumo = _cargar_todo()
    tabla_conversion = construir_tabla_conversion(df_ingredientes)

    df_necesidad_y_orden = calcular_necesidad_y_orden(
        df_ingredientes, df_inventario, df_orden, df_consumo
    )
    df_pedido_corregido = calcular_pedido_corregido(df_necesidad_y_orden, tabla_conversion)
    return agrupar_por_proveedor(df_pedido_corregido)


@router.get("/proyeccion/{sucursal}/{ingrediente_id}", response_model=ProyeccionDetalle)
def obtener_proyeccion(sucursal: str, ingrediente_id: str):
    """
    Devuelve el detalle completo de una proyección puntual: cuánto se
    proyecta, cuánto hay en inventario, cuánto se pidió y por qué
    método se calculó. Útil para el "por qué" detrás de cada alerta.
    """
    df_ingredientes, df_inventario, df_orden, df_consumo = _cargar_todo()

    if ingrediente_id not in set(df_ingredientes["ingrediente_id"]):
        raise HTTPException(status_code=404, detail=f"Ingrediente '{ingrediente_id}' no existe en el catálogo.")

    tabla_conversion = construir_tabla_conversion(df_ingredientes)
    info = tabla_conversion[ingrediente_id]

    historico = df_consumo[
        (df_consumo["sucursal"] == sucursal) & (df_consumo["ingrediente_id"] == ingrediente_id)
    ]
    if historico.empty:
        raise HTTPException(
            status_code=404, detail=f"No hay histórico para {sucursal} / {ingrediente_id}."
        )

    semanas = historico["semana"].str.replace("S", "", regex=False).astype(int).tolist()
    valores = historico["consumo_unidad_base"].tolist()
    resultado = proyectar_consumo(semanas, valores)

    inv = df_inventario[
        (df_inventario["sucursal"] == sucursal) & (df_inventario["ingrediente_id"] == ingrediente_id)
    ]
    inventario_actual = float(inv["stock_actual_unidad_base"].iloc[0]) if not inv.empty else 0.0
    necesidad_real = max(0.0, resultado.valor_proyectado - inventario_actual)

    orden = df_orden[
        (df_orden["sucursal"] == sucursal) & (df_orden["ingrediente_id"] == ingrediente_id)
    ]
    cantidad_pedida = (
        float(orden["cantidad_formatos"].iloc[0]) * info["factor"] if not orden.empty else 0.0
    )

    return ProyeccionDetalle(
        sucursal=sucursal,
        ingrediente=info["nombre"],
        consumo_proyectado=round(resultado.valor_proyectado, 1),
        inventario_actual=inventario_actual,
        necesidad_real=round(necesidad_real, 1),
        cantidad_pedida=round(cantidad_pedida, 1),
        unidad=info["unidad_base"],
        metodo=resultado.metodo,
        delta_vs_pedido=round(cantidad_pedida - necesidad_real, 1),
    )
