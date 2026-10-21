"""Provider selection and discovery, independent of dataset/query orchestration."""
import os
from dataclasses import dataclass

from backend import groq_client, ollama_client
from backend.config import GROQ_MODEL


@dataclass(frozen=True)
class AnalystModel:
    provider: str
    model: str

    @property
    def mode(self):
        return 'Groq cloud data analyst' if self.provider == 'groq' else 'Local data analyst'

    @property
    def scope(self):
        # Even identically named models at different providers have separate conversations.
        return f'{self.provider}:{self.model}'

    def chat(self, messages, **options):
        transport = groq_client if self.provider == 'groq' else ollama_client
        return transport.chat(self.model, messages, **options)


def resolve_model(provider, model):
    """Validate an explicit provider; never silently fall back or select cloud AI."""
    if not isinstance(model, str) or not model or len(model) > 200:
        raise ValueError('Choose an available AI model.')
    if provider == 'groq':
        if model != GROQ_MODEL:
            raise ValueError('Choose GPT-OSS 120B for the Groq provider.')
        if not groq_client.configured():
            raise ValueError('Set GROQ_API_KEY on the backend and restart it to enable Groq.')
    elif provider == 'ollama':
        try:
            models = ollama_client.local_models()
        except (OSError, ValueError):
            raise ValueError('Ollama is not available. Start Ollama or choose another answer mode.') from None
        if model not in models:
            raise ValueError('Choose a downloaded local Ollama model.')
    else:
        raise ValueError('Choose Ollama or Groq as the AI provider.')
    return AnalystModel(provider, model)


def available_models():
    """Expose local models and Groq configuration even when Ollama is offline."""
    try:
        models = ollama_client.local_models()
    except (OSError, ValueError, KeyError, TypeError):
        models = []
    options = [{'provider': 'ollama', 'model': model, 'label': f'{model} · Ollama (local)',
                'available': True} for model in models]
    groq_ready = groq_client.configured()
    options.append({'provider': 'groq', 'model': GROQ_MODEL,
                    'label': 'GPT-OSS 120B · Groq (cloud)', 'available': groq_ready})
    # Keep the original local-only list for older API clients.
    return {'models': models, 'options': options, 'groqConfigured': groq_ready, 'hosted': os.getenv('APP_ENV') == 'production'}
