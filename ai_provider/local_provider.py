"""本地模式 AI Provider

支持通过 Ollama 或 vLLM 部署的本地模型，使用 OpenAI Compatible API 协议进行调用。

支持的本地部署框架:
- Ollama: 默认端口 11434，API 路径 /v1/chat/completions
- vLLM: 默认端口 8000，API 路径 /v1/chat/completions

两者均兼容 OpenAI API 格式，因此使用统一的请求逻辑。
"""
import json
import logging
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
)

logger = logging.getLogger(__name__)


class LocalProvider(AIProvider):
    """本地模式 AI Provider（Ollama / vLLM）

    通过 OpenAI Compatible API 调用本地部署的模型。

    用法示例::

        config = ProviderConfig(
            base_url="http://localhost:11434/v1",
            model="qwen2.5-coder:7b",
            api_key="ollama",  # Ollama 占位符
        )
        provider = LocalProvider(config)
        response = provider.chat("请审查这段代码...")
    """

    def _build_url(self) -> str:
        """构建 chat completions API 地址"""
        base = self.config.base_url.rstrip("/")
        # 如果 base_url 已经包含 /v1，则直接追加路径
        if base.endswith("/v1"):
            return f"{base}/chat/completions"
        # 如果已包含完整路径
        if base.endswith("/chat/completions"):
            return base
        # 否则追加 /v1/chat/completions
        return f"{base}/v1/chat/completions"

    def _build_headers(self) -> dict:
        """构建请求头"""
        headers = {
            "Content-Type": "application/json",
        }
        if self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"
        return headers

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
        """执行本地模型推理请求

        Args:
            messages: 消息列表

        Returns:
            AIResponse: 推理响应

        Raises:
            ConnectionError: 无法连接本地服务
            AIProviderError: 其他调用错误
        """
        url = self._build_url()
        headers = self._build_headers()
        payload = self._build_payload(messages)

        logger.debug("请求 URL: %s", url)
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
                f"无法连接本地 AI 服务 ({self.config.base_url})。"
                f"请确认 Ollama/vLLM 服务已启动。错误: {e}"
            )
        except requests.exceptions.Timeout:
            raise ConnectionError(
                f"本地 AI 服务请求超时（{self.config.timeout}秒）。"
                f"模型推理可能需要更长时间，请尝试增大 timeout 配置。"
            )
        except requests.exceptions.RequestException as e:
            raise AIProviderError(f"请求本地 AI 服务失败: {e}")

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
            AIProviderError: 其他错误
        """
        try:
            error_data = resp.json()
            error_msg = error_data.get("error", {})
            if isinstance(error_msg, dict):
                error_msg = error_msg.get("message", str(error_data))
        except (json.JSONDecodeError, ValueError):
            error_msg = resp.text[:500]

        if resp.status_code in (401, 403):
            raise AuthenticationError(f"认证失败 ({resp.status_code}): {error_msg}")

        if resp.status_code == 404:
            raise AIProviderError(
                f"模型 '{self.config.model}' 未找到。"
                f"请检查模型名称或确认模型已下载。错误: {error_msg}"
            )

        raise AIProviderError(
            f"本地 AI 服务返回错误 ({resp.status_code}): {error_msg}"
        )

    def _parse_response(self, resp: requests.Response) -> AIResponse:
        """解析 API 响应

        Args:
            resp: HTTP 响应

        Returns:
            AIResponse: 结构化响应
        """
        try:
            data = resp.json()
        except (json.JSONDecodeError, ValueError) as e:
            raise AIProviderError(f"无法解析响应 JSON: {e}")

        # 提取内容
        choices = data.get("choices", [])
        if not choices:
            raise AIProviderError(f"API 响应中无 choices: {data}")

        content = choices[0].get("message", {}).get("content", "")

        # 提取 usage
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

    def test_connection(self) -> bool:
        """测试本地 AI 服务连接

        发送一个简单的请求验证服务是否可用。

        Returns:
            bool: 连接是否成功

        Raises:
            ConnectionError: 连接失败
        """
        logger.info("测试本地 AI 服务连接: %s (模型: %s)", self.config.base_url, self.config.model)

        try:
            response = self.chat("请回复：连接成功")
            if response.is_success:
                logger.info("本地 AI 服务连接成功！模型: %s", response.model)
                return True
            else:
                raise ConnectionError(f"连接测试失败: {response.error}")
        except AIProviderError as e:
            raise ConnectionError(f"本地 AI 服务连接测试失败: {e}")

    @property
    def provider_name(self) -> str:
        return "LocalProvider"
