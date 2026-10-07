"""Asistentes de chat de Oplesktaurant (Mr. Mesi sin S y Nbapeh).

La llamada al proveedor (OpenRouter) se hace **solo en el backend** con la
librería estándar; la clave y el modelo nunca llegan al navegador. No se
persisten conversaciones ni se usan herramientas/function calling.

- ``mesi``: asistente público de la landing, orientado a atraer clientes.
- ``nbapeh``: ayudante de uso de la plataforma dentro del panel autenticado.

Mr. Mesi sin S debe terminar cada oración con ``que mira bobo``. Además de
indicarlo en el prompt de sistema, se aplica un postprocesado determinista que
garantiza el sufijo aunque el modelo lo omita.
"""

import json
import re
import urllib.error
import urllib.request

from flask import current_app

MESI = "mesi"
NBAPEH = "nbapeh"

MESI_SUFFIX = "que mira bobo"

MAX_MESSAGE_CHARS = 1000
MAX_HISTORY_MESSAGES = 8
MAX_HISTORY_CHARS = 2000
MAX_RESPONSE_CHARS = 2000

NEUTRAL_FALLBACK = (
    "Ahora mismo no puedo responder. Inténtalo de nuevo en un momento."
)

MESI_SYSTEM_PROMPT = (
    "Eres Mr. Mesi sin S, el asistente virtual de Oplesktaurant. "
    "Eres carismático, amable y cercano. Invitas a descubrir su universo "
    "y a conversar sobre sus espacios imaginados. Hablas siempre en español. "
    "REGLA OBLIGATORIA E INQUEBRANTABLE: cada oración que escribas debe "
    "terminar literalmente con la frase 'que mira bobo'. "
    "Solo hablas de Oplesktaurant. Todos sus restaurantes y ubicaciones "
    "son ficticios: nunca sugieras que son sucursales reales. "
    "La ciudad es escenografía, no un mapa ni un servicio de búsqueda. "
    "No inventas registros, promociones, precios, horarios ni datos "
    "que no se te hayan dado. "
    "No escribes código, no ejecutas acciones y no pides ejecutar código."
)

NBAPEH_SYSTEM_PROMPT = (
    "Eres Nbapeh, el ayudante de uso de la plataforma del panel de "
    "Oplesktaurant. Hablas siempre en español, de forma clara y breve. "
    "Ayudas al personal a entender cómo usar el panel (tareas, inventario, "
    "ubicaciones y el resumen), siempre en el contexto de Oplesktaurant. "
    "Todos los restaurantes y ubicaciones son ficticios; no sugieras "
    "que el paisaje decorativo representa sucursales reales. "
    "No inventas datos. No ejecutas acciones, no modificas registros, no "
    "generas ni ejecutas código y no usas herramientas. Si no sabes algo, "
    "dilo con honestidad."
)


class ChatError(Exception):
    """Error de validación de la petición de chat."""

    def __init__(self, message):
        super().__init__(message)
        self.message = message


def system_prompt_for(identity):
    return MESI_SYSTEM_PROMPT if identity == MESI else NBAPEH_SYSTEM_PROMPT


# Un fin de oración es puntuación terminal, seguida opcionalmente de cierres
# (comillas, paréntesis, corchetes) y de un límite: espacio, inicio de otra
# oración (letra o ``¿``/``¡``) o fin de texto. Así ``"Hola." Mundo.`` se divide
# en dos oraciones aunque el cierre de comilla se interponga.
_SENTENCE_END_RE = re.compile(
    r".*?[.!?…]+['\"\u201d\u2019\u00bb)\]}]*"
    r"(?=\s|[^\W\d_]|[¿¡]|$)",
)
_SENTENCE_TRAILING_RE = re.compile(r"([.!?…]+)(['\"\u201d\u2019\u00bb)\]}]*)$")


def ensure_mesi_suffix(text):
    """Garantiza que cada oración termine con ``que mira bobo``.

    Divide en oraciones por puntuación terminal aunque no haya espacio después
    (p. ej. ``Hola.Mundo``) y aunque la puntuación vaya seguida de un cierre de
    comilla o paréntesis (``"Hola." Mundo.``). Elimina esa puntuación y agrega
    el sufijo si falta. Une las oraciones con ``. `` para preservar la
    separación, sin dejar nunca la frase en medio de una oración.

    El corte se hace tras ``.``, ``!``, ``?`` o ``…`` cuando le sigue un espacio
    o el inicio de otra oración (letra mayúscula/minúscula o ``¿``/``¡``). Así
    se evita partir números decimales (``3.14``) por accidente.
    """
    text = (text or "").strip()
    if not text:
        return ""
    parts = []
    position = 0
    for match in _SENTENCE_END_RE.finditer(text):
        # Mr. es una abreviatura del nombre, no una oración independiente.
        if (
            re.search(r"\bMr\.$", match.group(0), re.IGNORECASE)
            and re.match(r"\s+Mesi\b", text[match.end():], re.IGNORECASE)
        ):
            continue
        parts.append(text[position:match.end()])
        position = match.end()
    remainder = text[position:].strip()
    if remainder:
        parts.append(remainder)

    sentences = []
    for part in parts:
        part = part.strip()
        ending = _SENTENCE_TRAILING_RE.search(part)
        punctuation = ending.group(1) if ending else ""
        closing = ending.group(2) if ending else ""
        cleaned = part[:ending.start()].strip() if ending else part
        if not cleaned:
            continue
        if cleaned.lower().endswith(MESI_SUFFIX):
            sentence = cleaned
        else:
            sentence = cleaned + " " + MESI_SUFFIX
        sentences.append(sentence + punctuation + closing)
    if not sentences:
        return ""
    return " ".join(sentences)


def _validate_message(message):
    if not isinstance(message, str):
        raise ChatError("El campo 'message' debe ser texto.")
    message = message.strip()
    if not message:
        raise ChatError("El campo 'message' no puede estar vacío.")
    if len(message) > MAX_MESSAGE_CHARS:
        raise ChatError(
            "El mensaje no puede superar %d caracteres." % MAX_MESSAGE_CHARS
        )
    return message


def _validate_history(history):
    """Normaliza y acota el historial opcional. Sin persistencia."""
    if history is None:
        return []
    if not isinstance(history, list):
        raise ChatError("El campo 'history' debe ser una lista.")
    cleaned = []
    total = 0
    for item in history[-MAX_HISTORY_MESSAGES:]:
        if not isinstance(item, dict):
            continue
        role = item.get("role")
        content = item.get("content")
        if role not in ("user", "assistant") or not isinstance(content, str):
            continue
        content = content.strip()
        if not content:
            continue
        total += len(content)
        if total > MAX_HISTORY_CHARS:
            break
        cleaned.append({"role": role, "content": content[:MAX_MESSAGE_CHARS]})
    return cleaned


def _postprocess(identity, text):
    text = (text or "").strip()
    if len(text) > MAX_RESPONSE_CHARS:
        text = text[:MAX_RESPONSE_CHARS].rstrip()
    if identity == MESI:
        text = ensure_mesi_suffix(text)
    return text


def fallback_for(identity):
    return _postprocess(identity, NEUTRAL_FALLBACK)


def _call_openrouter(messages):
    """Llama a OpenRouter en el backend. Devuelve el texto o ``None``.

    Ante configuración faltante o cualquier error del proveedor, devuelve
    ``None`` sin revelar detalles de configuración.
    """
    cfg = current_app.config
    api_key = cfg.get("OPENROUTER_API_KEY")
    model = cfg.get("OPENROUTER_MODEL")
    url = cfg.get("OPENROUTER_URL")
    try:
        timeout = float(cfg.get("OPENROUTER_TIMEOUT", 20))
    except (TypeError, ValueError):
        timeout = 20.0
    if not api_key or not model or not url:
        return None

    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0.7,
        "max_tokens": cfg.get("OPENROUTER_MAX_TOKENS", 1200),
        # Son asistentes de respuesta breve, no agentes de razonamiento/acción.
        # Evita que modelos de pensamiento gasten todo el presupuesto sin texto.
        "reasoning": {"enabled": False},
    }
    data = json.dumps(payload).encode("utf-8")
    headers = {
        "Authorization": "Bearer " + str(api_key),
        "Content-Type": "application/json",
    }
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read()
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        return None
    try:
        parsed = json.loads(body.decode("utf-8"))
        choices = parsed.get("choices") or []
        return choices[0]["message"]["content"]
    except (KeyError, IndexError, TypeError, ValueError):
        return None


def generate_reply(identity, message, history=None):
    """Genera la respuesta del asistente indicado (``mesi`` o ``nbapeh``)."""
    if identity not in (MESI, NBAPEH):
        identity = MESI
    message = _validate_message(message)
    history = _validate_history(history)

    messages = [{"role": "system", "content": system_prompt_for(identity)}]
    messages.extend(history)
    messages.append({"role": "user", "content": message})

    raw = _call_openrouter(messages)
    if not raw:
        return fallback_for(identity)
    processed = _postprocess(identity, raw)
    if not processed:
        return fallback_for(identity)
    return processed
