from unittest.mock import MagicMock

import pytest

from app.core.chat import ChatNoDisponibleError, construir_contexto_datos, responder_pregunta
from main import app
from fastapi.testclient import TestClient

client = TestClient(app)


# --- Contexto: se construye con los datos reales, sin llamar a DeepSeek ---


def test_construir_contexto_incluye_resumen_de_alertas_real():
    contexto = construir_contexto_datos()
    assert contexto["resumen_alertas"]["total_alertas"] == 5
    assert contexto["resumen_alertas"]["insumos_olvidados"] == 1


def test_construir_contexto_incluye_las_88_proyecciones():
    contexto = construir_contexto_datos()
    assert len(contexto["proyecciones"]) == 88


def test_construir_contexto_metodo_es_string_no_enum():
    # json.dumps rompería si 'metodo' siguiera siendo un Enum de Python
    contexto = construir_contexto_datos()
    for fila in contexto["proyecciones"]:
        assert isinstance(fila["metodo"], str)


def test_construir_contexto_incluye_pedido_por_proveedor():
    contexto = construir_contexto_datos()
    proveedores = {p["proveedor"] for p in contexto["pedido_corregido_por_proveedor"]}
    assert "Molinos Central" in proveedores


def test_construir_contexto_es_serializable_a_json():
    import json

    contexto = construir_contexto_datos()
    # No debe lanzar TypeError por Enums, numpy types, etc.
    json.dumps(contexto, ensure_ascii=False)


# --- responder_pregunta: sin API key configurada ---


def test_responder_pregunta_sin_api_key_lanza_error(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    with pytest.raises(ChatNoDisponibleError, match="DEEPSEEK_API_KEY"):
        responder_pregunta("¿qué sucursal tiene más alertas?")


# --- responder_pregunta: con DeepSeek mockeado (no hay salida de red en este entorno) ---


def _mock_openai_client(texto_respuesta: str):
    mock_choice = MagicMock()
    mock_choice.message.content = texto_respuesta
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]

    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = mock_response
    return mock_client


def test_responder_pregunta_devuelve_el_texto_del_mock(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "fake-key-para-test")
    mock_client = _mock_openai_client("Costa del Este tiene el riesgo de quiebre más grande.")
    monkeypatch.setattr("app.core.chat.OpenAI", lambda **kwargs: mock_client)

    respuesta = responder_pregunta("¿qué sucursal tiene el riesgo de quiebre más grande?")

    assert respuesta == "Costa del Este tiene el riesgo de quiebre más grande."
    mock_client.chat.completions.create.assert_called_once()


def test_responder_pregunta_manda_el_contexto_en_el_system_prompt(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "fake-key-para-test")
    mock_client = _mock_openai_client("respuesta de prueba")
    monkeypatch.setattr("app.core.chat.OpenAI", lambda **kwargs: mock_client)

    responder_pregunta("¿algo?")

    kwargs_llamada = mock_client.chat.completions.create.call_args.kwargs
    system_msg = kwargs_llamada["messages"][0]["content"]
    assert "aji_chombo" in system_msg or "Molinos Central" in system_msg  # dato real en el contexto


def test_responder_pregunta_respuesta_vacia_lanza_error(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "fake-key-para-test")
    mock_client = _mock_openai_client("")
    monkeypatch.setattr("app.core.chat.OpenAI", lambda **kwargs: mock_client)

    with pytest.raises(ChatNoDisponibleError):
        responder_pregunta("¿algo?")


# --- Endpoint /api/chat ---


def test_endpoint_chat_sin_api_key_devuelve_503(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    response = client.post("/api/chat", json={"pregunta": "¿qué alertas hay?"})
    assert response.status_code == 503


def test_endpoint_chat_ok_con_mock(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "fake-key-para-test")
    mock_client = _mock_openai_client("Hay 5 alertas esta semana.")
    monkeypatch.setattr("app.core.chat.OpenAI", lambda **kwargs: mock_client)

    response = client.post("/api/chat", json={"pregunta": "¿cuántas alertas hay?"})

    assert response.status_code == 200
    assert response.json() == {"respuesta": "Hay 5 alertas esta semana."}


def test_endpoint_chat_pregunta_vacia_devuelve_422():
    response = client.post("/api/chat", json={"pregunta": ""})
    assert response.status_code == 422


def test_endpoint_chat_falta_el_campo_pregunta_devuelve_422():
    response = client.post("/api/chat", json={})
    assert response.status_code == 422
