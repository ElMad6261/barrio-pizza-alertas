"""
Chat con los datos.

Principio de diseño central: DeepSeek NO calcula nada. Todo el número
que aparece en una respuesta del chat ya fue calculado por el pipeline
determinístico de este backend (proyección, necesidad real, alertas,
pedido corregido) — el modelo solo lo interpreta y lo traduce a
lenguaje natural. Esto evita que el chat invente cifras que no
coinciden con el resto del dashboard.

Estrategia de contexto: con 4 sucursales y 22 ingredientes, todo el
dataset calculado entra cómodo en un solo prompt — no hace falta RAG
ni embeddings para este volumen de datos.
"""

import json
import os

from openai import APIConnectionError, APIError, OpenAI

from app.core.alertas import calcular_necesidad_y_orden, construir_resumen_proyecciones, generar_alertas
from app.core.data_loader import (
    cargar_consumo_historico,
    cargar_ingredientes,
    cargar_inventario,
    cargar_orden,
    validar_datos,
)
from app.core.pedido_corregido import agrupar_por_proveedor, calcular_pedido_corregido
from app.core.unidades import construir_tabla_conversion

MODELO_DEEPSEEK = "deepseek-chat"
DEEPSEEK_BASE_URL = "https://api.deepseek.com"

SYSTEM_PROMPT_TEMPLATE = """Sos un asistente que ayuda a la gerente de compras de Barrio Pizza \
a interpretar los datos de alertas y proyecciones de la semana actual.

Reglas estrictas:
- Respondé SOLO en base a los datos en formato JSON que se te dan a continuación. \
No inventes cifras ni asumas datos que no estén ahí.
- Si la pregunta no se puede responder con estos datos, decilo explícitamente en \
vez de adivinar.
- Respondé en español, de forma breve, clara y accionable — quien te lee no es \
técnica y no tiene tiempo de leer tablas.
- No repitas el JSON en tu respuesta, solo la conclusión en texto plano.

Datos de esta semana:
{contexto}"""


class ChatNoDisponibleError(Exception):
    """La API de DeepSeek no está configurada o no respondió correctamente."""


def construir_contexto_datos() -> dict:
    """
    Arma un dict con todo lo que el chat puede necesitar para responder:
    el mismo resumen de alertas, proyecciones y pedido corregido que ya
    ve el resto del dashboard — ninguna fuente de verdad nueva.
    """
    df_ingredientes = cargar_ingredientes()
    df_inventario = cargar_inventario()
    df_orden = cargar_orden()
    df_consumo = cargar_consumo_historico()
    tabla_conversion = construir_tabla_conversion(df_ingredientes)

    reporte_calidad = validar_datos(df_ingredientes, df_inventario, df_orden, df_consumo)
    resumen_alertas = generar_alertas(
        df_ingredientes, df_inventario, df_orden, df_consumo, reporte_calidad
    )

    df_necesidad = calcular_necesidad_y_orden(df_ingredientes, df_inventario, df_orden, df_consumo)

    proyecciones = construir_resumen_proyecciones(df_necesidad, tabla_conversion)
    # 'metodo' llega como Enum -> pasar a string plano para que json.dumps no rompa
    proyecciones_serializables = [
        {**fila, "metodo": fila["metodo"].value if hasattr(fila["metodo"], "value") else fila["metodo"]}
        for fila in proyecciones
    ]

    df_pedido_corregido = calcular_pedido_corregido(df_necesidad, tabla_conversion)
    pedido_por_proveedor = agrupar_por_proveedor(df_pedido_corregido)

    return {
        "resumen_alertas": resumen_alertas.model_dump(),
        "proyecciones": proyecciones_serializables,
        "pedido_corregido_por_proveedor": [p.model_dump() for p in pedido_por_proveedor],
    }


def responder_pregunta(pregunta: str) -> str:
    """
    Arma el contexto, se lo manda a DeepSeek junto con la pregunta, y
    devuelve la respuesta en texto plano.

    Nota de costo/abuso: no hay rate limiting acá — para el alcance de
    este reto no hace falta, pero en producción esto le pega a una API
    paga por cada llamada y valdría la pena limitarlo.
    """
    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        raise ChatNoDisponibleError(
            "Falta configurar la variable de entorno DEEPSEEK_API_KEY en el servidor."
        )

    contexto = construir_contexto_datos()
    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(contexto=json.dumps(contexto, ensure_ascii=False))

    client = OpenAI(api_key=api_key, base_url=DEEPSEEK_BASE_URL)

    try:
        respuesta = client.chat.completions.create(
            model=MODELO_DEEPSEEK,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": pregunta},
            ],
            temperature=0.2,
            max_tokens=500,
        )
    except (APIError, APIConnectionError) as error:
        raise ChatNoDisponibleError(f"No se pudo contactar a DeepSeek: {error}") from error

    contenido = respuesta.choices[0].message.content
    if not contenido:
        raise ChatNoDisponibleError("DeepSeek devolvió una respuesta vacía.")

    return contenido.strip()
