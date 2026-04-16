"""AI Provider 抽象基类

定义所有 AI 推理提供者的统一接口规范。
本地模式（Ollama/vLLM）和云端模式（OpenAI/阿里云百炼）均需实现此接口。
"""
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class AIMessage:
    """AI 对话消息"""

    role: str
    """消息角色: system / user / assistant"""

    content: str
    """消息内容"""


@dataclass
class AIResponse:
    """AI 推理响应结果"""

    content: str
    """AI 返回的文本内容"""

    model: str = ""
    """实际使用的模型名称"""

    usage: Dict[str, int] = field(default_factory=dict)
    """Token 使用量: prompt_tokens, completion_tokens, total_tokens"""

    raw_response: Optional[Dict[str, Any]] = None
    """原始 API 响应（用于调试）"""

    elapsed_seconds: float = 0.0
    """请求耗时（秒）"""

    error: Optional[str] = None
    """错误信息（如有）"""

    @property
    def is_success(self) -> bool:
        """请求是否成功"""
        return self.error is None and self.content != ""

    @property
    def prompt_tokens(self) -> int:
        return self.usage.get("prompt_tokens", 0)

    @property
    def completion_tokens(self) -> int:
        return self.usage.get("completion_tokens", 0)

    @property
    def total_tokens(self) -> int:
        return self.usage.get("total_tokens", 0)

    def summary(self) -> str:
        """响应摘要"""
        if self.error:
            return f"[错误] {self.error}"
        content_preview = self.content[:80] + "..." if len(self.content) > 80 else self.content
        return (
            f"[成功] 模型={self.model}, "
            f"Token={self.total_tokens}, "
            f"耗时={self.elapsed_seconds:.1f}s, "
            f"内容={content_preview}"
        )


@dataclass
class ProviderConfig:
    """AI Provider 配置"""

    base_url: str
    """API 服务地址"""

    model: str
    """模型名称"""

    api_key: str = ""
    """API Key（本地模式可为空或占位符）"""

    temperature: float = 0.3
    """生成温度（0-2），越低越确定性"""

    max_tokens: int = 4096
    """最大生成 Token 数"""

    timeout: int = 120
    """请求超时时间（秒）"""

    max_retries: int = 3
    """最大重试次数"""

    retry_delay: float = 2.0
    """重试间隔（秒）"""

    def validate(self) -> List[str]:
        """验证配置项，返回错误列表"""
        errors = []
        if not self.base_url:
            errors.append("base_url 不能为空")
        if not self.model:
            errors.append("model 不能为空")
        if not self.base_url.startswith(("http://", "https://")):
            errors.append(f"base_url 格式无效: {self.base_url}")
        if self.temperature < 0 or self.temperature > 2:
            errors.append(f"temperature 范围应为 0-2, 当前值: {self.temperature}")
        if self.max_tokens < 1:
            errors.append(f"max_tokens 应大于 0, 当前值: {self.max_tokens}")
        return errors


class AIProviderError(Exception):
    """AI Provider 异常基类"""
    pass


class ConnectionError(AIProviderError):
    """连接异常"""
    pass


class AuthenticationError(AIProviderError):
    """认证异常（API Key 无效等）"""
    pass


class RateLimitError(AIProviderError):
    """速率限制异常"""
    pass


class AIProvider(ABC):
    """AI 推理提供者抽象基类

    所有 AI 模型接入都需继承此类并实现抽象方法。
    基类提供了统一的重试机制和错误处理。

    用法示例::

        class MyProvider(AIProvider):
            def _do_chat(self, messages):
                # 实现具体的 API 调用
                ...

            def test_connection(self):
                # 实现连接测试
                ...

        provider = MyProvider(config)
        response = provider.chat("请审查这段代码...")
    """

    def __init__(self, config: ProviderConfig):
        """初始化

        Args:
            config: Provider 配置

        Raises:
            AIProviderError: 配置验证失败
        """
        errors = config.validate()
        if errors:
            raise AIProviderError(f"配置验证失败: {'; '.join(errors)}")
        self.config = config

    def chat(self, prompt: str, system_prompt: Optional[str] = None) -> AIResponse:
        """发送对话请求（带重试机制）

        Args:
            prompt: 用户提示词
            system_prompt: 系统提示词（可选）

        Returns:
            AIResponse: AI 响应结果
        """
        messages = []
        if system_prompt:
            messages.append(AIMessage(role="system", content=system_prompt))
        messages.append(AIMessage(role="user", content=prompt))

        return self.chat_with_messages(messages)

    def chat_with_messages(self, messages: List[AIMessage]) -> AIResponse:
        """发送多轮对话请求（带重试机制）

        Args:
            messages: 消息列表

        Returns:
            AIResponse: AI 响应结果
        """
        last_error = None

        for attempt in range(1, self.config.max_retries + 1):
            start_time = time.time()
            try:
                logger.info(
                    "AI 推理请求 (第%d/%d次): 模型=%s, 消息数=%d",
                    attempt, self.config.max_retries, self.config.model, len(messages),
                )
                response = self._do_chat(messages)
                response.elapsed_seconds = time.time() - start_time
                logger.info("AI 推理成功: %s", response.summary())
                return response

            except AuthenticationError as e:
                # 认证错误不重试
                elapsed = time.time() - start_time
                logger.error("AI 推理失败（不可重试）: %s", e)
                return AIResponse(
                    content="",
                    model=self.config.model,
                    elapsed_seconds=elapsed,
                    error=str(e),
                )

            except ConnectionError as e:
                # 网络连接错误可重试
                last_error = e
                elapsed = time.time() - start_time
                logger.warning(
                    "AI 推理失败-连接错误 (第%d/%d次, 耗时%.1fs): %s",
                    attempt, self.config.max_retries, elapsed, e,
                )
                if attempt < self.config.max_retries:
                    delay = self.config.retry_delay * attempt
                    logger.info("等待 %.1f 秒后重试...", delay)
                    time.sleep(delay)

            except AIProviderError as e:
                # 其他 Provider 错误不重试（如模型不存在、响应解析失败等）
                elapsed = time.time() - start_time
                logger.error("AI 推理失败（不可重试）: %s", e)
                return AIResponse(
                    content="",
                    model=self.config.model,
                    elapsed_seconds=elapsed,
                    error=str(e),
                )

            except Exception as e:
                last_error = e
                elapsed = time.time() - start_time
                logger.warning(
                    "AI 推理失败 (第%d/%d次, 耗时%.1fs): %s",
                    attempt, self.config.max_retries, elapsed, e,
                )
                if attempt < self.config.max_retries:
                    delay = self.config.retry_delay * attempt  # 递增延迟
                    logger.info("等待 %.1f 秒后重试...", delay)
                    time.sleep(delay)

        # 所有重试均失败
        return AIResponse(
            content="",
            model=self.config.model,
            elapsed_seconds=0,
            error=f"重试 {self.config.max_retries} 次后仍失败: {last_error}",
        )

    @abstractmethod
    def _do_chat(self, messages: List[AIMessage]) -> AIResponse:
        """执行实际的 AI 推理请求（子类实现）

        Args:
            messages: 消息列表

        Returns:
            AIResponse: 响应结果

        Raises:
            AIProviderError: 调用失败
        """
        ...

    @abstractmethod
    def test_connection(self) -> bool:
        """测试与 AI 服务的连接

        Returns:
            bool: 连接是否成功

        Raises:
            ConnectionError: 连接失败
            AuthenticationError: 认证失败
        """
        ...

    @property
    def provider_name(self) -> str:
        """Provider 名称（用于日志和展示）"""
        return self.__class__.__name__

    def __repr__(self) -> str:
        return f"{self.provider_name}(model={self.config.model}, base_url={self.config.base_url})"
