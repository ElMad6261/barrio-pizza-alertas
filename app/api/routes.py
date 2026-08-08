"""
Endpoints de la API.

Todos los endpoints leen los CSV de data/ en cada llamada. Para el
volumen de datos del reto (4 sucursales, 22 ingredientes) esto es
instantáneo; si en el futuro esto crece o se conecta a un ERP como
Odoo, este es el punto donde se cambiaría por una lectura cacheada o
por una llamada al API del ERP en vez de a los CSV.
"""

from fastapi import APIRouter, HTTPException

from app.core.alertas import calcular_necesidad_y_orden, construir_resumen_proyecciones, generar_alertas
from app.core.chat import ChatNoDisponibleError, responder_pregunta
from app.core.data_loader import (
    cargar_consumo_historico,
    cargar_ingredientes,
    cargar_inventario,
    cargar_orden,
    listar_proveedores,
    listar_sucursales,
    validar_datos,
)
from app.core.pedido_corregido import agrupar_por_proveedor, calcular_pedido_corregido
from app.core.proyeccion import proyectar_consumo
from app.core.unidades import construir_tabla_conversion
from app.models.schemas import (
    IngredienteInfo,
    PedidoPorProveedor,
    PreguntaChat,
    ProyeccionDetalle,
    ProyeccionResumen,
    PuntoHistorico,
    ResumenSemanal,
    RespuestaChat,
)

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


@router.get("/sucursales", response_model=list[str])
def obtener_sucursales():
    """Sucursales válidas, para poblar filtros/dropdowns sin hardcodear nada en el frontend."""
    _, df_inventario, _, _ = _cargar_todo()
    return listar_sucursales(df_inventario)


@router.get("/proveedores", response_model=list[str])
def obtener_proveedores():
    """Proveedores del catálogo, útil para filtros del pedido corregido."""
    df_ingredientes, _, _, _ = _cargar_todo()
    return listar_proveedores(df_ingredientes)


@router.get("/ingredientes", response_model=list[IngredienteInfo])
def obtener_ingredientes():
    """Catálogo completo de ingredientes, para dropdowns o búsquedas en el frontend."""
    df_ingredientes, _, _, _ = _cargar_todo()
    return [
        IngredienteInfo(
            ingrediente_id=fila["ingrediente_id"],
            nombre=fila["nombre"],
            proveedor=fila["proveedor"],
            unidad_base=fila["unidad_base"],
            formato_compra=fila["formato_compra"],
            es_perecedero=bool(fila["es_perecedero"]),
        )
        for _, fila in df_ingredientes.sort_values("nombre").iterrows()
    ]


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

    sucursales_validas = listar_sucursales(df_inventario)
    if sucursal not in sucursales_validas:
        raise HTTPException(
            status_code=404,
            detail=f"Sucursal '{sucursal}' no existe. Sucursales válidas: {sucursales_validas}",
        )

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


@router.get("/proyecciones", response_model=list[ProyeccionResumen])
def obtener_proyecciones(sucursal: str | None = None):
    """
    Devuelve la proyección de las combinaciones sucursal-ingrediente (las
    88 del catálogo, o solo las de una sucursal si se pasa ?sucursal=).
    Pensado para poblar una tabla completa sin llamar 88 veces al
    endpoint de detalle.
    """
    df_ingredientes, df_inventario, df_orden, df_consumo = _cargar_todo()
    tabla_conversion = construir_tabla_conversion(df_ingredientes)
    df = calcular_necesidad_y_orden(df_ingredientes, df_inventario, df_orden, df_consumo)

    if sucursal is not None:
        sucursales_validas = listar_sucursales(df_inventario)
        if sucursal not in sucursales_validas:
            raise HTTPException(
                status_code=404,
                detail=f"Sucursal '{sucursal}' no existe. Sucursales válidas: {sucursales_validas}",
            )
        df = df[df["sucursal"] == sucursal]

    filas = construir_resumen_proyecciones(df, tabla_conversion)
    return [ProyeccionResumen(**f) for f in filas]


@router.get("/proyeccion/{sucursal}/{ingrediente_id}", response_model=ProyeccionDetalle)
def obtener_proyeccion(sucursal: str, ingrediente_id: str):
    """
    Devuelve el detalle completo de una proyección puntual: cuánto se
    proyecta, cuánto hay en inventario, cuánto se pidió, por qué método
    se calculó, la confianza (r2) y el histórico semana a semana con
    las semanas excluidas marcadas — todo lo necesario para graficar
    el "por qué" detrás de una alerta puntual.
    """
    df_ingredientes, df_inventario, df_orden, df_consumo = _cargar_todo()

    sucursales_validas = listar_sucursales(df_inventario)
    if sucursal not in sucursales_validas:
        raise HTTPException(
            status_code=404,
            detail=f"Sucursal '{sucursal}' no existe. Sucursales válidas: {sucursales_validas}",
        )

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

    puntos_historico = [
        PuntoHistorico(semana=s, consumo=v, es_outlier=s in resultado.semanas_excluidas)
        for s, v in sorted(zip(semanas, valores))
    ]

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
        ingrediente_id=ingrediente_id,
        consumo_proyectado=round(resultado.valor_proyectado, 1),
        inventario_actual=inventario_actual,
        necesidad_real=round(necesidad_real, 1),
        cantidad_pedida=round(cantidad_pedida, 1),
        unidad=info["unidad_base"],
        metodo=resultado.metodo,
        r2=resultado.r2,
        semanas_excluidas=resultado.semanas_excluidas,
        delta_vs_pedido=round(cantidad_pedida - necesidad_real, 1),
        historico=puntos_historico,
    )


@router.post("/chat", response_model=RespuestaChat)
def chat_con_los_datos(cuerpo: PreguntaChat):
    """
    Responde preguntas en español sobre las alertas, proyecciones y el
    pedido corregido de la semana actual. DeepSeek solo interpreta los
    datos que ya calculó este backend — no hace ningún cálculo propio,
    para que nunca contradiga lo que muestra el resto del dashboard.
    """
    try:
        respuesta = responder_pregunta(cuerpo.pregunta)
    except ChatNoDisponibleError as error:
        raise HTTPException(status_code=503, detail=str(error))
    return RespuestaChat(respuesta=respuesta)
