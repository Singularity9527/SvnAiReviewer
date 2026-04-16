"""AI Provider 单元测试

通过 Mock 模拟 HTTP 请求，测试各 Provider 的逻辑正确性。
无需真实 AI 服务即可运行。
"""
import sys
import os
import json
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from ai_provider.base import (
    AIMessage,
    AIProvider,
    AIProviderError,
    AIResponse,
    AuthenticationError,
    ProviderConfig,
    RateLimitError,
)
from ai_provider.local_provider import LocalProvider
from ai_provider.cloud_provider import CloudProvider
from ai_provider.factory import ProviderFactory


# ============================================================
# ProviderConfig 测试
# ============================================================

class TestProviderConfig(unittest.TestCase):
    """配置验证测试"""

    def test_valid_config(self):
        config = ProviderConfig(
            base_url="http://localhost:11434/v1",
            model="qwen2.5-coder:7b",
        )
        errors = config.validate()
        self.assertEqual(errors, [])

    def test_empty_base_url(self):
        config = ProviderConfig(base_url="", model="test")
        errors = config.validate()
        self.assertTrue(any("base_url" in e for e in errors))

    def test_empty_model(self):
        config = ProviderConfig(base_url="http://localhost:11434/v1", model="")
        errors = config.validate()
        self.assertTrue(any("model" in e for e in errors))

    def test_invalid_url_format(self):
        config = ProviderConfig(base_url="localhost:11434", model="test")
        errors = config.validate()
        self.assertTrue(any("格式无效" in e for e in errors))

    def test_invalid_temperature(self):
        config = ProviderConfig(
            base_url="http://localhost:11434/v1",
            model="test",
            temperature=3.0,
        )
        errors = config.validate()
        self.assertTrue(any("temperature" in e for e in errors))


# ============================================================
# AIResponse 测试
# ============================================================

class TestAIResponse(unittest.TestCase):
    """AIResponse 数据模型测试"""

    def test_success_response(self):
        resp = AIResponse(content="审查结果", model="gpt-4o")
        self.assertTrue(resp.is_success)

    def test_error_response(self):
        resp = AIResponse(content="", model="gpt-4o", error="连接失败")
        self.assertFalse(resp.is_success)

    def test_usage_properties(self):
        resp = AIResponse(
            content="ok",
            usage={"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
        )
        self.assertEqual(resp.prompt_tokens, 100)
        self.assertEqual(resp.completion_tokens, 50)
        self.assertEqual(resp.total_tokens, 150)

    def test_summary_success(self):
        resp = AIResponse(content="审查完成", model="test", elapsed_seconds=2.5)
        summary = resp.summary()
        self.assertIn("成功", summary)
        self.assertIn("2.5s", summary)

    def test_summary_error(self):
        resp = AIResponse(content="", error="timeout")
        summary = resp.summary()
        self.assertIn("错误", summary)


# ============================================================
# LocalProvider 测试
# ============================================================

class TestLocalProvider(unittest.TestCase):
    """本地模式 Provider 测试"""

    def _make_provider(self, **kwargs):
        config = ProviderConfig(
            base_url="http://localhost:11434/v1",
            model="qwen2.5-coder:7b",
            api_key="ollama",
            max_retries=1,
            **kwargs,
        )
        return LocalProvider(config)

    def _mock_success_response(self):
        """构造成功响应的 Mock"""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "id": "chatcmpl-123",
            "model": "qwen2.5-coder:7b",
            "choices": [
                {"message": {"role": "assistant", "content": "代码审查结果..."}}
            ],
            "usage": {
                "prompt_tokens": 100,
                "completion_tokens": 200,
                "total_tokens": 300,
            },
        }
        return mock_resp

    @patch("ai_provider.local_provider.requests.post")
    def test_chat_success(self, mock_post):
        mock_post.return_value = self._mock_success_response()
        provider = self._make_provider()

        response = provider.chat("请审查代码")
        self.assertTrue(response.is_success)
        self.assertEqual(response.content, "代码审查结果...")
        self.assertEqual(response.total_tokens, 300)

    @patch("ai_provider.local_provider.requests.post")
    def test_chat_with_system_prompt(self, mock_post):
        mock_post.return_value = self._mock_success_response()
        provider = self._make_provider()

        response = provider.chat("请审查代码", system_prompt="你是代码审查专家")
        self.assertTrue(response.is_success)

        # 验证请求体包含 system 消息
        call_kwargs = mock_post.call_args
        payload = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
        messages = payload["messages"]
        self.assertEqual(messages[0]["role"], "system")
        self.assertEqual(messages[1]["role"], "user")

    @patch("ai_provider.local_provider.requests.post")
    def test_connection_error(self, mock_post):
        import requests as req
        mock_post.side_effect = req.exceptions.ConnectionError("Connection refused")
        provider = self._make_provider()

        response = provider.chat("test")
        self.assertFalse(response.is_success)
        self.assertIn("无法连接", response.error)

    @patch("ai_provider.local_provider.requests.post")
    def test_timeout_error(self, mock_post):
        import requests as req
        mock_post.side_effect = req.exceptions.ReadTimeout("Request timed out")
        provider = self._make_provider()

        response = provider.chat("test")
        self.assertFalse(response.is_success)
        self.assertIn("超时", response.error)

    @patch("ai_provider.local_provider.requests.post")
    def test_model_not_found(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_resp.json.return_value = {"error": {"message": "model not found"}}
        mock_post.return_value = mock_resp
        provider = self._make_provider()

        response = provider.chat("test")
        self.assertFalse(response.is_success)
        self.assertIn("未找到", response.error)

    def test_build_url_with_v1(self):
        provider = self._make_provider()
        url = provider._build_url()
        self.assertEqual(url, "http://localhost:11434/v1/chat/completions")

    def test_build_url_without_v1(self):
        config = ProviderConfig(
            base_url="http://localhost:8000",
            model="codellama",
            max_retries=1,
        )
        provider = LocalProvider(config)
        url = provider._build_url()
        self.assertEqual(url, "http://localhost:8000/v1/chat/completions")


# ============================================================
# CloudProvider 测试
# ============================================================

class TestCloudProvider(unittest.TestCase):
    """云端模式 Provider 测试"""

    def _make_provider(self, **kwargs):
        config = ProviderConfig(
            base_url="https://api.openai.com/v1",
            model="gpt-4o",
            api_key="sk-test1234567890abcdef",
            max_retries=1,
            **kwargs,
        )
        return CloudProvider(config)

    def _mock_success_response(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "id": "chatcmpl-456",
            "model": "gpt-4o",
            "choices": [
                {"message": {"role": "assistant", "content": "云端审查结果"}}
            ],
            "usage": {
                "prompt_tokens": 200,
                "completion_tokens": 400,
                "total_tokens": 600,
            },
        }
        return mock_resp

    def test_missing_api_key_raises(self):
        with self.assertRaises(AIProviderError):
            config = ProviderConfig(
                base_url="https://api.openai.com/v1",
                model="gpt-4o",
                api_key="",
            )
            CloudProvider(config)

    def test_placeholder_api_key_raises(self):
        with self.assertRaises(AIProviderError):
            config = ProviderConfig(
                base_url="https://api.openai.com/v1",
                model="gpt-4o",
                api_key="sk-...",
            )
            CloudProvider(config)

    @patch("ai_provider.cloud_provider.requests.post")
    def test_chat_success(self, mock_post):
        mock_post.return_value = self._mock_success_response()
        provider = self._make_provider()

        response = provider.chat("请审查代码")
        self.assertTrue(response.is_success)
        self.assertEqual(response.content, "云端审查结果")
        self.assertEqual(response.total_tokens, 600)

    @patch("ai_provider.cloud_provider.requests.post")
    def test_auth_error_no_retry(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        mock_resp.json.return_value = {"error": {"message": "Invalid API key"}}
        mock_post.return_value = mock_resp

        config = ProviderConfig(
            base_url="https://api.openai.com/v1",
            model="gpt-4o",
            api_key="sk-invalid_key_12345678",
            max_retries=3,  # 认证错误不应重试
        )
        provider = CloudProvider(config)
        response = provider.chat("test")

        self.assertFalse(response.is_success)
        self.assertIn("认证失败", response.error)
        # 认证错误不重试，只调用一次
        self.assertEqual(mock_post.call_count, 1)

    @patch("ai_provider.cloud_provider.requests.post")
    def test_rate_limit_error(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 429
        mock_resp.headers = {"Retry-After": "30"}
        mock_resp.json.return_value = {"error": {"message": "Rate limit exceeded"}}
        mock_post.return_value = mock_resp
        provider = self._make_provider()

        response = provider.chat("test")
        self.assertFalse(response.is_success)
        self.assertIn("频率超限", response.error)

    def test_mask_api_key(self):
        provider = self._make_provider()
        masked = provider._mask_api_key()
        self.assertNotIn("test1234567890abcdef", masked)
        self.assertTrue(masked.startswith("sk-t"))
        self.assertTrue(masked.endswith("cdef"))

    def test_detect_openai_provider(self):
        provider = self._make_provider()
        name = provider._detect_provider_name()
        self.assertEqual(name, "OpenAI")

    def test_detect_aliyun_provider(self):
        config = ProviderConfig(
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
            model="qwen-plus",
            api_key="sk-test1234567890abcdef",
        )
        provider = CloudProvider(config)
        name = provider._detect_provider_name()
        self.assertEqual(name, "阿里云百炼")

    def test_build_url_aliyun(self):
        config = ProviderConfig(
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
            model="qwen-plus",
            api_key="sk-test1234567890abcdef",
        )
        provider = CloudProvider(config)
        url = provider._build_url()
        self.assertTrue(url.endswith("/chat/completions"))


# ============================================================
# ProviderFactory 测试
# ============================================================

class TestProviderFactory(unittest.TestCase):
    """工厂类测试"""

    def test_create_local_provider(self):
        provider = ProviderFactory.create(
            mode="local",
            base_url="http://localhost:11434/v1",
            model="qwen2.5-coder:7b",
        )
        self.assertIsInstance(provider, LocalProvider)

    def test_create_cloud_provider(self):
        provider = ProviderFactory.create(
            mode="cloud",
            base_url="https://api.openai.com/v1",
            model="gpt-4o",
            api_key="sk-test1234567890abcdef",
        )
        self.assertIsInstance(provider, CloudProvider)

    def test_invalid_mode_raises(self):
        with self.assertRaises(AIProviderError):
            ProviderFactory.create(
                mode="invalid",
                base_url="http://localhost",
                model="test",
            )

    def test_create_from_config_local(self):
        config = {
            "ai_mode": "local",
            "local": {
                "base_url": "http://localhost:11434/v1",
                "model": "qwen2.5-coder:7b",
                "api_key": "ollama",
            },
        }
        provider = ProviderFactory.create_from_config(config)
        self.assertIsInstance(provider, LocalProvider)

    def test_create_from_config_cloud(self):
        config = {
            "ai_mode": "cloud",
            "cloud": {
                "base_url": "https://api.openai.com/v1",
                "model": "gpt-4o",
                "api_key": "sk-test1234567890abcdef",
            },
        }
        provider = ProviderFactory.create_from_config(config)
        self.assertIsInstance(provider, CloudProvider)

    def test_missing_ai_mode_raises(self):
        with self.assertRaises(AIProviderError):
            ProviderFactory.create_from_config({"local": {}})

    def test_missing_mode_config_raises(self):
        with self.assertRaises(AIProviderError):
            ProviderFactory.create_from_config({"ai_mode": "local"})

    def test_create_with_extra_kwargs(self):
        provider = ProviderFactory.create(
            mode="local",
            base_url="http://localhost:11434/v1",
            model="test",
            temperature=0.5,
            max_tokens=2048,
        )
        self.assertEqual(provider.config.temperature, 0.5)
        self.assertEqual(provider.config.max_tokens, 2048)

    def test_list_available_modes(self):
        modes = ProviderFactory.list_available_modes()
        self.assertIn("local", modes)
        self.assertIn("cloud", modes)

    def test_get_default_config(self):
        local_default = ProviderFactory.get_default_config("local")
        self.assertIn("base_url", local_default)
        self.assertIn("model", local_default)

        cloud_default = ProviderFactory.get_default_config("cloud")
        self.assertIn("api_key", cloud_default)


# ============================================================
# 重试机制测试
# ============================================================

class TestRetryMechanism(unittest.TestCase):
    """重试机制测试"""

    @patch("ai_provider.local_provider.requests.post")
    def test_retry_on_network_error(self, mock_post):
        """网络错误应触发重试"""
        import requests as req

        # 第一次失败，第二次成功
        success_resp = MagicMock()
        success_resp.status_code = 200
        success_resp.json.return_value = {
            "model": "test",
            "choices": [{"message": {"content": "ok"}}],
            "usage": {},
        }

        mock_post.side_effect = [
            req.exceptions.ConnectionError("fail"),
            success_resp,
        ]

        config = ProviderConfig(
            base_url="http://localhost:11434/v1",
            model="test",
            max_retries=2,
            retry_delay=0.01,  # 缩短测试等待
        )
        provider = LocalProvider(config)
        response = provider.chat("test")

        self.assertTrue(response.is_success)
        self.assertEqual(mock_post.call_count, 2)


if __name__ == "__main__":
    unittest.main()
