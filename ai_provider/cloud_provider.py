"""云端模式 AI Provider

支持通过 API Key 调用云端大模型服务：
- OpenAI API (GPT-4, GPT-4o 等)
- 阿里云百炼 (Qwen-Plus, Qwen-Max 等)
- 其他兼容 OpenAI API 格式的云端服务

与 LocalProvider 的区别：
1. API Key 为必填项
2. 增加速率限制处理（429 Too Many Requests）
3. 增加敏感信息保护（日志中隐藏 API Key）
"""
import json
import logging
import time
from typing import List

import requests

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

logger = logging.getLogger(__name__)


class CloudProvider(AIProvider):
    """云端模式 AI Provider

    通过标准 OpenAI API 格式调用云端大模型。

    用法示例::

        config = ProviderConfig(
            base_url="https://api.openai.com/v1",
            model="gpt-4o",
            api_key="sk-...",
        )
        provider = CloudProvider(config)
        response = provider.chat("请审查这段代码...")
    """

    # 已知的云端服务商地址映射
    _KNOWN_PROVIDERS = {
        "api.openai.com": "OpenAI",
        "dashscope.aliyuncs.com": "阿里云百炼",
        "api.anthropic.com": "Anthropic",
        "api.deepseek.com": "DeepSeek",
    }

    def __init__(self, config: ProviderConfig):
        """初始化云端 Provider

        Args:
            config: Provider 配置

        Raises:
            AIProviderError: 配置验证失败（如缺少 API Key）
        """
        if not config.api_key or config.api_key in ("", "sk-..."):
            raise AIProviderError(
                "云端模式需要有效的 API Key。"
                "请通过 'svn-ai config' 命令设置。"
            )
        super().__init__(config)

    def _build_url(self) -> str:
        """构建 chat completions API 地址"""
        base = self.config.base_url.rstrip("/")
        if base.endswith("/chat/completions"):
            return base
        if base.endswith("/v1"):
            return f"{base}/chat/completions"
        # 阿里云百炼等兼容模式
        if "compatible-mode" in base:
            return f"{base}/chat/completions"
        return f"{base}/v1/chat/completions"

    def _build_headers(self) -> dict:
        """构建请求头"""
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.config.api_key}",
        }

    def _build_payload(self, messages: List[AIMessage]) -> dict:
        """构建请求体"""
        return {
            "model": self.config.model,
            "messages": [
                {"role": msg.role, "content": msg.content}
                for msg in messages
            ],
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_tokens,
        }

    def _do_chat(self, messages: List[AIMessage]) -> AIResponse:
        """执行云端模型推理请求

        Args:
            messages: 消息列表

        Returns:
            AIResponse: 推理响应

        Raises:
            AuthenticationError: API Key 无效
            RateLimitError: 请求频率超限
            ConnectionError: 网络连接失败
            AIProviderError: 其他调用错误
        """
        url = self._build_url()
        headers = self._build_headers()
        payload = self._build_payload(messages)

        provider_name = self._detect_provider_name()
        logger.debug("请求云端服务 [%s]: %s", provider_name, url)
        logger.debug("请求模型: %s", self.config.model)

        try:
            resp = requests.post(
                url,
                headers=headers,
                json=payload,
                timeout=self.config.timeout,
            )
        except requests.exceptions.ConnectionError as e:
            raise ConnectionError(
                f"无法连接云端 AI 服务 ({provider_name})。"
                f"请检查网络连接。错误: {e}"
            )
        except requests.exceptions.Timeout:
            raise ConnectionError(
                f"云端 AI 服务请求超时（{self.config.timeout}秒）。"
                f"请尝试增大 timeout 配置或检查网络状况。"
            )
        except requests.exceptions.RequestException as e:
            raise AIProviderError(f"请求云端服务失败: {e}")

        # 处理 HTTP 错误
        if resp.status_code != 200:
            self._handle_error_response(resp)

        # 解析响应
        return self._parse_response(resp)

    def _handle_error_response(self, resp: requests.Response) -> None:
        """处理错误响应

        Args:
            resp: HTTP 响应

        Raises:
            AuthenticationError: 401/403
            RateLimitError: 429
            AIProviderError: 其他错误
        """
        try:
            error_data = resp.json()
            error_msg = error_data.get("error", {})
            if isinstance(error_msg, dict):
                error_msg = error_msg.get("message", str(error_data))
        except (json.JSONDecodeError, ValueError):
            error_msg = resp.text[:500]

        masked_key = self._mask_api_key()
        provider_name = self._detect_provider_name()

        if resp.status_code in (401, 403):
            raise AuthenticationError(
                f"[{provider_name}] API Key 认证失败 (Key: {masked_key})。"
                f"请检查 API Key 是否正确。错误: {error_msg}"
            )

        if resp.status_code == 429:
            # 尝试获取重试时间
            retry_after = resp.headers.get("Retry-After", "未知")
            raise RateLimitError(
                f"[{provider_name}] 请求频率超限。"
                f"建议等待 {retry_after} 秒后重试。错误: {error_msg}"
            )

        if resp.status_code == 404:
            raise AIProviderError(
                f"[{provider_name}] 模型 '{self.config.model}' 不可用。"
                f"请检查模型名称是否正确。错误: {error_msg}"
            )

        raise AIProviderError(
            f"[{provider_name}] 服务返回错误 ({resp.status_code}): {error_msg}"
        )

    def _parse_response(self, resp: requests.Response) -> AIResponse:
        """解析 API 响应"""
        try:
            data = resp.json()
        except (json.JSONDecodeError, ValueError) as e:
            raise AIProviderError(f"无法解析响应 JSON: {e}")

        choices = data.get("choices", [])
        if not choices:
            raise AIProviderError(f"API 响应中无 choices: {data}")

        content = choices[0].get("message", {}).get("content", "")

        usage_data = data.get("usage", {})
        usage = {
            "prompt_tokens": usage_data.get("prompt_tokens", 0),
            "completion_tokens": usage_data.get("completion_tokens", 0),
            "total_tokens": usage_data.get("total_tokens", 0),
        }

        return AIResponse(
            content=content,
            model=data.get("model", self.config.model),
            usage=usage,
            raw_response=data,
        )

    def _mask_api_key(self) -> str:
        """隐藏 API Key，只显示前4位和后4位"""
        key = self.config.api_key
        if len(key) <= 8:
            return "****"
        return f"{key[:4]}...{key[-4:]}"

    def _detect_provider_name(self) -> str:
        """根据 base_url 检测云端服务商名称"""
        for domain, name in self._KNOWN_PROVIDERS.items():
            if domain in self.config.base_url:
                return name
        return "云端服务"

    def test_connection(self) -> bool:
        """测试云端 AI 服务连接

        Returns:
            bool: 连接是否成功

        Raises:
            ConnectionError: 连接失败
            AuthenticationError: 认证失败
        """
        provider_name = self._detect_provider_name()
        logger.info(
            "测试云端 AI 服务连接: %s (模型: %s, 服务商: %s)",
            self.config.base_url, self.config.model, provider_name,
        )

        try:
            response = self.chat("请回复：连接成功")
            if response.is_success:
                logger.info(
                    "[%s] 连接成功！模型: %s, Token用量: %d",
                    provider_name, response.model, response.total_tokens,
                )
                return True
            else:
                raise ConnectionError(f"[{provider_name}] 连接测试失败: {response.error}")
        except AIProviderError as e:
            raise ConnectionError(f"[{provider_name}] 连接测试失败: {e}")

    @property
    def provider_name(self) -> str:
        return f"CloudProvider({self._detect_provider_name()})"
