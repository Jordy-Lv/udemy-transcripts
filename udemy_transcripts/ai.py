"""Backend de la API de Claude para `--study api` (el SDK `anthropic` es opcional)."""

import json
from dataclasses import dataclass, field
from typing import List, Optional

from .errors import UdemyError

DEFAULT_MODEL = "claude-opus-5-5"
MAX_OUTPUT_TOKENS = 16000          # sin streaming: por debajo del tope de tiempo de los SDK
FALLBACK_BETA = "server-side-fallback-2026-07-01"

# id → (USD/MTok de entrada, USD/MTok de salida, admite `effort`, admite `fallbacks`)
# Precios de la lista oficial de modelos (primer nivel de precio); son una estimación.
MODELS = {
    "claude-fable-5-1": (10.00, 50.00, True, True),
    "claude-fable-5": (10.00, 50.00, True, False),
    "claude-opus-5-5": (4.00, 20.00, True, True),
    "claude-opus-5": (5.00, 25.00, True, True),
    "claude-opus-4-8": (5.00, 25.00, True, False),
    "claude-opus-4-7": (5.00, 25.00, True, False),
    "claude-opus-4-6": (5.00, 25.00, True, False),
    "claude-sonnet-5-5": (2.00, 10.00, True, True),
    "claude-sonnet-5": (2.00, 10.00, True, False),
    "claude-sonnet-4-6": (3.00, 15.00, True, False),
    "claude-haiku-5-5": (0.10, 0.50, True, False),
    "claude-haiku-4-5": (1.00, 5.00, False, False),
}

SECTION_SCHEMA = {
    "type": "object",
    "properties": {
        "resumen": {"type": "string"},
        "flashcards": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "pregunta": {"type": "string"},
                    "respuesta": {"type": "string"},
                    "etiquetas": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["pregunta", "respuesta", "etiquetas"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["resumen", "flashcards"],
    "additionalProperties": False,
}


class StudyError(UdemyError):
    """Fallo de una sección concreta: se anota y se sigue con la siguiente."""


class FatalStudyError(UdemyError):
    """Fallo que se repetiría en todas las secciones (credenciales, petición inválida)."""


def model_info(model):
    """(entrada, salida, effort, fallbacks) del modelo, o None si no lo conocemos."""
    return MODELS.get(model)


@dataclass
class Generation:
    resumen: str
    flashcards: List[dict] = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0
    served_by: Optional[str] = None


class AnthropicBackend:
    """Una llamada por trozo de sección, con salida JSON validada por esquema."""

    def __init__(self, model=DEFAULT_MODEL, client=None, log=print):
        self.model = model
        self.log = log
        self.info = model_info(model)
        if client is None:
            try:
                import anthropic
            except ImportError:
                raise UdemyError("Falta el SDK de Anthropic. Instálalo con:\n"
                                 "    pip install \"udemy-transcripts[ai]\"   (requiere Python 3.10+)")
            client = anthropic.Anthropic(max_retries=4)
        self.client = client
        self._fallback_ok = bool(self.info and self.info[3])
        if self._fallback_ok:
            log("  ℹ Fallback del servidor activado: si el modelo rechaza una petición, "
                "Anthropic la repite con otro modelo.")

    # ---- petición ------------------------------------------------------
    def _request(self, system, user):
        kwargs = dict(
            model=self.model, max_tokens=MAX_OUTPUT_TOKENS, system=system,
            messages=[{"role": "user", "content": user}],
            output_config=self._output_config())
        if self._fallback_ok:
            try:
                return self.client.beta.messages.create(
                    betas=[FALLBACK_BETA], fallbacks="default", **kwargs)
            except TypeError:               # SDK sin soporte de `fallbacks`: sin fallback
                self._fallback_ok = False
        return self.client.messages.create(**kwargs)

    def _output_config(self):
        config = {"format": {"type": "json_schema", "schema": SECTION_SCHEMA}}
        if self.info is None or self.info[2]:
            config["effort"] = "low"        # resumir/extraer no necesita razonar a fondo
        return config

    def generate(self, system, user):
        try:
            response = self._request(system, user)
        except Exception as exc:            # errores tipados del SDK, sin importarlo arriba
            raise _translate(exc)
        return _parse(response)


def _translate(exc):
    """Errores del SDK → los nuestros (los que se repetirían en cada sección son fatales)."""
    name = type(exc).__name__
    detail = getattr(exc, "message", None) or str(exc)
    if name in ("AuthenticationError", "PermissionDeniedError") or \
            "could not resolve authentication method" in detail.lower():
        return FatalStudyError(
            "Anthropic no aceptó las credenciales. Define ANTHROPIC_API_KEY (o inicia sesión "
            f"con `ant auth login`). Detalle: {detail}")
    if name in ("BadRequestError", "NotFoundError", "UnprocessableEntityError"):
        return FatalStudyError(f"La API rechazó la petición ({name}): {detail}")
    if name == "RateLimitError":
        return StudyError(f"Límite de peticiones de Anthropic ({detail}); repite más tarde: lo "
                          "ya generado queda en caché.")
    return StudyError(f"Error de la API de Anthropic ({name}): {detail}")


def _parse(response):
    stop = getattr(response, "stop_reason", None)
    if stop == "refusal":
        details = getattr(response, "stop_details", None)
        category = getattr(details, "category", None)
        raise StudyError("El modelo rechazó la petición"
                         + (f" (categoría: {category})" if category else "") + ".")
    if stop == "max_tokens":
        raise StudyError("La respuesta se cortó por longitud (max_tokens): la sección es muy "
                         "larga; prueba con otro modelo o divídela con --sections.")
    text = next((b.text for b in response.content if getattr(b, "type", "") == "text"), None)
    try:
        data = json.loads(text)
    except (TypeError, ValueError):
        raise StudyError("La respuesta no es JSON válido.")
    if not isinstance(data, dict) or not isinstance(data.get("resumen"), str):
        raise StudyError("La respuesta no trae el campo «resumen».")
    cards = [c for c in data.get("flashcards") or [] if isinstance(c, dict)
             and str(c.get("pregunta", "")).strip() and str(c.get("respuesta", "")).strip()]
    usage = getattr(response, "usage", None)
    return Generation(
        resumen=data["resumen"].strip(),
        flashcards=[{"pregunta": str(c["pregunta"]).strip(), "respuesta": str(c["respuesta"]).strip(),
                     "etiquetas": [str(t) for t in c.get("etiquetas") or []]} for c in cards],
        input_tokens=int(getattr(usage, "input_tokens", 0) or 0),
        output_tokens=int(getattr(usage, "output_tokens", 0) or 0),
        served_by=getattr(response, "model", None))
