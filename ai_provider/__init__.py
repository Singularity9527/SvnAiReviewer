"""AI Provider 模块

提供统一的 AI 推理接口，支持本地（Ollama/vLLM）和云端（OpenAI/阿里云百炼）两种模式。
"""
from .base import (
    AIMessage,
    AIProvider,
    AIProviderError,
    AIResponse,
    AuthenticationError,
    ConnectionError,
    ProviderConfig,
    RateLimitError,
)
from .local_provider import LocalProvider
from .cloud_provider import CloudProvider
from .factory import ProviderFactory

__all__ = [
    "AIMessage",
    "AIProvider",
    "AIProviderError",
    "AIResponse",
    "AuthenticationError",
    "ConnectionError",
    "ProviderConfig",
    "RateLimitError",
    "LocalProvider",
    "CloudProvider",
    "ProviderFactory",
]
