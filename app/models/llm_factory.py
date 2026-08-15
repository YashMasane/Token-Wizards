import os
import logging
from typing import Optional
from langchain_core.language_models.chat_models import BaseChatModel
from app.config import settings

logger = logging.getLogger(__name__)


class LLMConfigurationError(RuntimeError):
    """
    Raised when the LLM cannot be initialised — missing API key, import error,
    or connectivity failure.  This is intentionally NOT caught silently; it must
    surface to the user so the misconfiguration is visible and actionable.
    """


def get_llm(
    provider: Optional[str] = None,
    model_name: Optional[str] = None,
    temperature: float = 0.0,
) -> BaseChatModel:
    """
    Factory function returning a model-agnostic ChatModel instance.
    Supports Groq, OpenAI, and Ollama.

    Raises LLMConfigurationError (a subclass of RuntimeError) if the provider
    cannot be initialised. Callers MUST NOT swallow this exception silently —
    it must propagate so the user sees a clear failure message instead of a
    fake hardcoded response.
    """
    resolved_provider = (provider or settings.LLM_PROVIDER).lower()

    # ── Groq ────────────────────────────────────────────────────────────────
    if resolved_provider == "groq":
        api_key = settings.GROQ_API_KEY or os.getenv("GROQ_API_KEY")
        if not api_key:
            raise LLMConfigurationError(
                "GROQ_API_KEY is not set. "
                "Add it to your .env file or set the environment variable, then restart the server."
            )
        try:
            from langchain_groq import ChatGroq
            target_model = model_name or settings.GROQ_MODEL_NAME
            logger.info(f"[LLMFactory] Initialising ChatGroq — model: {target_model}")
            return ChatGroq(
                groq_api_key=api_key,
                model_name=target_model,
                temperature=temperature,
            )
        except LLMConfigurationError:
            raise
        except Exception as e:
            raise LLMConfigurationError(
                f"Failed to initialise ChatGroq "
                f"(model={model_name or settings.GROQ_MODEL_NAME}): {e}. "
                "Check that langchain-groq is installed and the API key is valid."
            ) from e

    # ── OpenAI ──────────────────────────────────────────────────────────────
    elif resolved_provider == "openai":
        api_key = settings.OPENAI_API_KEY or os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise LLMConfigurationError(
                "OPENAI_API_KEY is not set. "
                "Add it to your .env file or set the environment variable, then restart the server."
            )
        try:
            from langchain_openai import ChatOpenAI
            target_model = model_name or settings.OPENAI_MODEL_NAME
            logger.info(f"[LLMFactory] Initialising ChatOpenAI — model: {target_model}")
            return ChatOpenAI(
                openai_api_key=api_key,
                model_name=target_model,
                temperature=temperature,
            )
        except LLMConfigurationError:
            raise
        except Exception as e:
            raise LLMConfigurationError(
                f"Failed to initialise ChatOpenAI "
                f"(model={model_name or settings.OPENAI_MODEL_NAME}): {e}. "
                "Check that langchain-openai is installed and the API key is valid."
            ) from e

    # ── Ollama ──────────────────────────────────────────────────────────────
    elif resolved_provider == "ollama":
        try:
            from langchain_community.chat_models import ChatOllama
            target_model = model_name or settings.OLLAMA_MODEL_NAME
            logger.info(
                f"[LLMFactory] Initialising ChatOllama — model: {target_model} "
                f"at {settings.OLLAMA_BASE_URL}"
            )
            return ChatOllama(
                base_url=settings.OLLAMA_BASE_URL,
                model=target_model,
                temperature=temperature,
            )
        except Exception as e:
            raise LLMConfigurationError(
                f"Failed to initialise ChatOllama "
                f"(model={model_name or settings.OLLAMA_MODEL_NAME}, "
                f"base_url={settings.OLLAMA_BASE_URL}): {e}. "
                "Ensure Ollama is running locally and langchain-community is installed."
            ) from e

    # ── Unknown provider ─────────────────────────────────────────────────────
    else:
        raise LLMConfigurationError(
            f"Unknown LLM provider '{resolved_provider}'. "
            "Set LLM_PROVIDER in your .env to one of: groq, openai, ollama."
        )


def check_llm_health() -> dict:
    """
    Attempts a lightweight test invocation of the configured LLM to confirm
    it is reachable and the API key is valid.

    Returns a dict:
        {
            "status": "ok" | "error",
            "provider": str,
            "model": str,
            "message": str
        }
    Called at startup and also surfaced via GET /api/health.
    """
    provider = settings.LLM_PROVIDER.lower()
    model = (
        settings.GROQ_MODEL_NAME
        if provider == "groq"
        else (
            settings.OPENAI_MODEL_NAME
            if provider == "openai"
            else settings.OLLAMA_MODEL_NAME
        )
    )
    try:
        llm = get_llm()
        # Minimal test — one short reply is enough to confirm auth + connectivity
        response = llm.invoke([{"role": "user", "content": "ping"}])
        if not response or not response.content:
            raise ValueError("LLM returned an empty response during health check.")
        logger.info(f"[LLMFactory] Health check PASSED — provider={provider}, model={model}")
        return {
            "status": "ok",
            "provider": provider,
            "model": model,
            "message": "LLM is reachable and responding.",
        }
    except LLMConfigurationError as e:
        logger.error(f"[LLMFactory] Health check FAILED (configuration error): {e}")
        return {"status": "error", "provider": provider, "model": model, "message": str(e)}
    except Exception as e:
        logger.error(f"[LLMFactory] Health check FAILED (runtime error): {e}")
        return {
            "status": "error",
            "provider": provider,
            "model": model,
            "message": f"LLM connectivity error: {e}",
        }
