"""AI Provider 工厂模块

根据配置自动创建对应的 AI Provider 实例。
支持通过配置字典或 YAML 配置文件创建。
"""
import logging
from typing import Any, Dict, Optional

from .base import AIProvider, AIProviderError, ProviderConfig
from .local_provider import LocalProvider
from .cloud_provider import CloudProvider

logger = logging.getLogger(__name__)

# 模式到 Provider 类的映射
_PROVIDER_MAP = {
    "local": LocalProvider,
    "cloud": CloudProvider,
}


class ProviderFactory:
    """AI Provider 工厂类

    根据配置创建对应模式的 Provider 实例。

    用法示例::

        # 从字典配置创建
        provider = ProviderFactory.create(
            mode="local",
            base_url="http://localhost:11434/v1",
            model="qwen2.5-coder:7b",
        )

        # 从完整配置字典创建
        config = {
            "ai_mode": "cloud",
            "cloud": {
                "base_url": "https://api.openai.com/v1",
                "model": "gpt-4o",
                "api_key": "sk-...",
            }
        }
        provider = ProviderFactory.create_from_config(config)
    """

    @staticmethod
    def create(
        mode: str,
        base_url: str,
        model: str,
        api_key: str = "",
        **kwargs,
    ) -> AIProvider:
        """创建 AI Provider 实例

        Args:
            mode: 模式 ('local' 或 'cloud')
            base_url: API 服务地址
            model: 模型名称
            api_key: API Key
            **kwargs: 其他 ProviderConfig 参数 (temperature, max_tokens, timeout 等)

        Returns:
            AIProvider: Provider 实例

        Raises:
            AIProviderError: 模式无效或配置错误
        """
        mode = mode.lower().strip()

        if mode not in _PROVIDER_MAP:
            available = ", ".join(_PROVIDER_MAP.keys())
            raise AIProviderError(
                f"未知的 AI 模式: '{mode}'。可用模式: {available}"
            )

        config = ProviderConfig(
            base_url=base_url,
            model=model,
            api_key=api_key,
            **kwargs,
        )

        provider_class = _PROVIDER_MAP[mode]
        logger.info("创建 %s Provider: 模型=%s, 地址=%s", mode, model, base_url)

        return provider_class(config)

    @staticmethod
    def create_from_config(config_dict: Dict[str, Any]) -> AIProvider:
        """从完整配置字典创建 Provider

        配置字典格式与 config.yaml 对应::

            {
                "ai_mode": "local",  # 或 "cloud"
                "local": {
                    "base_url": "http://localhost:11434/v1",
                    "model": "qwen2.5-coder:7b",
                    "api_key": "ollama",
                },
                "cloud": {
                    "base_url": "https://api.openai.com/v1",
                    "model": "gpt-4o",
                    "api_key": "sk-...",
                },
            }

        Args:
            config_dict: 配置字典

        Returns:
            AIProvider: Provider 实例

        Raises:
            AIProviderError: 配置无效
        """
        mode = config_dict.get("ai_mode", "").lower().strip()

        if not mode:
            raise AIProviderError("配置中缺少 'ai_mode' 字段")

        if mode not in _PROVIDER_MAP:
            available = ", ".join(_PROVIDER_MAP.keys())
            raise AIProviderError(
                f"未知的 ai_mode: '{mode}'。可用值: {available}"
            )

        mode_config = config_dict.get(mode)
        if not mode_config or not isinstance(mode_config, dict):
            raise AIProviderError(
                f"配置中缺少 '{mode}' 配置块。"
                f"请在配置文件中添加 '{mode}' 相关配置。"
            )

        base_url = mode_config.get("base_url", "")
        model = mode_config.get("model", "")
        api_key = mode_config.get("api_key", "")

        # 提取可选参数
        extra_kwargs = {}
        for key in ("temperature", "max_tokens", "timeout", "max_retries", "retry_delay"):
            if key in mode_config:
                extra_kwargs[key] = mode_config[key]

        return ProviderFactory.create(
            mode=mode,
            base_url=base_url,
            model=model,
            api_key=api_key,
            **extra_kwargs,
        )

    @staticmethod
    def list_available_modes() -> list:
        """列出所有可用模式"""
        return list(_PROVIDER_MAP.keys())

    @staticmethod
    def get_default_config(mode: str) -> Dict[str, Any]:
        """获取指定模式的默认配置模板

        Args:
            mode: 模式名称

        Returns:
            dict: 默认配置
        """
        defaults = {
            "local": {
                "base_url": "http://localhost:11434/v1",
                "model": "qwen2.5-coder:7b",
                "api_key": "ollama",
            },
            "cloud": {
                "base_url": "https://api.openai.com/v1",
                "model": "gpt-4o",
                "api_key": "sk-...",
            },
        }
        return defaults.get(mode, {})
