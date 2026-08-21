"""
Thin REST wrapper around the Groq API for LLM text generation.

Why Groq instead of Gemini for generation?
  The Gemini generativelanguage.googleapis.com endpoint is geo-blocked
  in Myanmar (and some other countries), so deployments there hit a
  connection timeout on every chatbot request regardless of API key
  validity. Groq's API (api.groq.com) is accessible from Myanmar and
  offers generous free-tier limits. See docs/DECISIONS.md Decision 33.

This module is a drop-in replacement for gemini_client.generate_text():
  - Same interface: generate_text(prompt, system_instruction) → str
  - Same error class: raises GeminiError (re-exported as GroqError) so
    pipeline.py and chatbot.py need zero changes.
  - No Groq SDK required — plain requests, same style as gemini_client.py.

Model: defaults to meta-llama/llama-4-scout-17b-16e-instruct via the
Groq OpenAI-compatible endpoint. Override via GROQ_MODEL in .env.

Embedding: Groq does not provide embedding APIs. The BM25 retrieval
arm of HybridRetriever is always available and is the primary retriever.
The Gemini embedding arm (search_embeddings in hybrid_retriever.py) will
silently return [] when GEMINI_API_KEY is absent — this is already the
expected fallback path and requires no code changes.
"""
import os

import requests

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_MODEL   = os.getenv("GROQ_MODEL", "meta-llama/llama-4-scout-17b-16e-instruct")
GROQ_BASE_URL = "https://api.groq.com/openai/v1/chat/completions"
TIMEOUT_SECONDS = 30  # Groq is fast; 30 s is generous


class GroqError(Exception):
    """Raised for any Groq API problem. Intentionally has the same
    interface as GeminiError so callers that catch GeminiError can
    be updated to catch both with a single except clause."""


# Re-export as GeminiError alias so pipeline.py/chatbot.py need zero changes.
GeminiError = GroqError


def is_configured() -> bool:
    return bool(GROQ_API_KEY)


def _headers():
    return {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {GROQ_API_KEY}",
    }


def _raise_with_body(e: requests.RequestException, action: str):
    """Surface a clean error from a Groq HTTP failure."""
    resp = getattr(e, "response", None)
    if resp is not None:
        try:
            status  = resp.status_code
            body    = resp.json()
            err_msg = body.get("error", {}).get("message", "")

            if status == 429:
                raise GroqError(
                    f"Groq rate limit reached. {err_msg or 'Try again in a moment.'}"
                ) from e
            if status >= 500:
                short = err_msg.split(".")[0] if err_msg else "service temporarily unavailable"
                raise GroqError(
                    f"Groq is temporarily unavailable — {short.lower().strip()}. "
                    f"Please try again in a moment."
                ) from e
            raise GroqError(
                f"Groq {action} failed ({status}): {err_msg or resp.text[:300]}"
            ) from e
        except GroqError:
            raise
        except Exception:
            pass
    raise GroqError(f"Groq {action} request failed: {e}") from e


def generate_text(prompt: str, system_instruction: str = None) -> str:
    """Call Groq chat completions and return plain text.

    Uses the OpenAI-compatible /v1/chat/completions endpoint.
    system_instruction maps to the 'system' role message.
    """
    if not is_configured():
        raise GroqError("GROQ_API_KEY is not set.")

    messages = []
    if system_instruction:
        messages.append({"role": "system", "content": system_instruction})
    messages.append({"role": "user", "content": prompt})

    body = {
        "model":       GROQ_MODEL,
        "messages":    messages,
        "temperature": 0.3,        # low temp for factual SOP answers
        "max_tokens":  1024,
    }

    try:
        resp = requests.post(
            GROQ_BASE_URL,
            headers=_headers(),
            json=body,
            timeout=TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
        data = resp.json()

        choices = data.get("choices") or []
        if not choices:
            raise GroqError(f"No choices in Groq response: {data}")

        text = choices[0].get("message", {}).get("content", "")
        if not text:
            raise GroqError(f"Empty content in Groq response: {data}")
        return text

    except requests.RequestException as e:
        _raise_with_body(e, "chat/completions")
