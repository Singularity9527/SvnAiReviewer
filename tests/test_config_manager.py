"""配置管理器单元测试"""
import sys
import os
import tempfile
import unittest

import yaml

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from config_manager import (
    ConfigManager,
    ConfigError,
    ConfigValidationError,
    DEFAULT_CONFIG,
)


class TestConfigManagerLoad(unittest.TestCase):
    """配置加载测试"""

    def test_load_from_file(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False, encoding="utf-8") as f:
            yaml.dump({"ai_mode": "local", "local": {"base_url": "http://localhost:11434/v1", "model": "test", "api_key": "ollama"}}, f)
            path = f.name

        try:
            mgr = ConfigManager(config_path=path)
            config = mgr.load()
            self.assertEqual(config["ai_mode"], "local")
            self.assertTrue(mgr.is_loaded)
        finally:
            os.unlink(path)

    def test_load_nonexistent_raises(self):
        mgr = ConfigManager(config_path="/nonexistent/config.yaml")
        # find_config 在指定路径不存在时会搜索其他路径，需确保无匹配
        # 当工作目录存在 config.yaml 时不会报错，因此测用不存在的目录
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            fake_path = os.path.join(tmpdir, "nonexist_sub", "config.yaml")
            mgr2 = ConfigManager(config_path=fake_path)
            with self.assertRaises(ConfigError):
                mgr2.load()

    def test_load_nonexistent_with_defaults(self):
        mgr = ConfigManager(config_path="/nonexistent/config.yaml")
        config = mgr.load(use_defaults=True)
        self.assertEqual(config["ai_mode"], "local")
        self.assertTrue(mgr.is_loaded)

    def test_load_invalid_yaml(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False, encoding="utf-8") as f:
            f.write(": invalid: yaml: {{[")
            path = f.name

        try:
            mgr = ConfigManager(config_path=path)
            with self.assertRaises(ConfigError):
                mgr.load()
        finally:
            os.unlink(path)

    def test_load_empty_file_with_defaults(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False, encoding="utf-8") as f:
            f.write("")
            path = f.name

        try:
            mgr = ConfigManager(config_path=path)
            config = mgr.load(use_defaults=True)
            self.assertEqual(config["ai_mode"], "local")
        finally:
            os.unlink(path)


class TestConfigManagerSave(unittest.TestCase):
    """配置保存测试"""

    def test_save_and_reload(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "config.yaml")

            mgr = ConfigManager()
            mgr.reset_to_defaults()
            mgr.set("ai_mode", "cloud")
            mgr.set("cloud.api_key", "sk-test123456789abc")
            saved = mgr.save(path)

            self.assertEqual(saved, path)
            self.assertTrue(os.path.exists(path))

            # 重新加载验证
            mgr2 = ConfigManager(config_path=path)
            config = mgr2.load()
            self.assertEqual(config["ai_mode"], "cloud")
            self.assertEqual(config["cloud"]["api_key"], "sk-test123456789abc")

    def test_save_creates_directory(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "sub", "dir", "config.yaml")

            mgr = ConfigManager()
            mgr.reset_to_defaults()
            mgr.save(path)

            self.assertTrue(os.path.exists(path))


class TestConfigManagerGetSet(unittest.TestCase):
    """get/set 测试"""

    def setUp(self):
        self.mgr = ConfigManager()
        self.mgr.reset_to_defaults()

    def test_get_simple_key(self):
        self.assertEqual(self.mgr.get("ai_mode"), "local")

    def test_get_nested_key(self):
        self.assertEqual(self.mgr.get("local.model"), "qwen2.5-coder:7b")

    def test_get_default(self):
        self.assertEqual(self.mgr.get("nonexistent", "default_val"), "default_val")

    def test_get_nested_default(self):
        self.assertEqual(self.mgr.get("local.nonexistent", 42), 42)

    def test_set_simple_key(self):
        self.mgr.set("ai_mode", "cloud")
        self.assertEqual(self.mgr.get("ai_mode"), "cloud")

    def test_set_nested_key(self):
        self.mgr.set("cloud.api_key", "sk-new")
        self.assertEqual(self.mgr.get("cloud.api_key"), "sk-new")

    def test_set_creates_nested_path(self):
        self.mgr.set("new.nested.key", "value")
        self.assertEqual(self.mgr.get("new.nested.key"), "value")


class TestConfigManagerValidation(unittest.TestCase):
    """配置验证测试"""

    def test_valid_local_config(self):
        mgr = ConfigManager()
        mgr.reset_to_defaults()
        errors = mgr.validate()
        self.assertEqual(errors, [])

    def test_missing_ai_mode(self):
        mgr = ConfigManager()
        mgr._config = {"local": {"base_url": "http://localhost:11434/v1", "model": "test"}}
        mgr._loaded = True
        errors = mgr.validate()
        self.assertTrue(any("ai_mode" in e for e in errors))

    def test_invalid_ai_mode(self):
        mgr = ConfigManager()
        mgr._config = {"ai_mode": "invalid"}
        mgr._loaded = True
        errors = mgr.validate()
        self.assertTrue(any("无效" in e for e in errors))

    def test_missing_mode_config(self):
        mgr = ConfigManager()
        mgr._config = {"ai_mode": "local"}
        mgr._loaded = True
        errors = mgr.validate()
        self.assertTrue(any("配置块" in e for e in errors))

    def test_missing_base_url(self):
        mgr = ConfigManager()
        mgr._config = {"ai_mode": "local", "local": {"model": "test", "base_url": ""}}
        mgr._loaded = True
        errors = mgr.validate()
        self.assertTrue(any("base_url" in e for e in errors))

    def test_invalid_url_format(self):
        mgr = ConfigManager()
        mgr._config = {"ai_mode": "local", "local": {"model": "test", "base_url": "invalid-url"}}
        mgr._loaded = True
        errors = mgr.validate()
        self.assertTrue(any("格式无效" in e for e in errors))

    def test_cloud_missing_api_key(self):
        mgr = ConfigManager()
        mgr._config = {
            "ai_mode": "cloud",
            "cloud": {"base_url": "https://api.openai.com/v1", "model": "gpt-4o", "api_key": "sk-..."}
        }
        mgr._loaded = True
        errors = mgr.validate()
        self.assertTrue(any("api_key" in e.lower() or "API Key" in e for e in errors))

    def test_cloud_valid_config(self):
        mgr = ConfigManager()
        mgr._config = {
            "ai_mode": "cloud",
            "cloud": {"base_url": "https://api.openai.com/v1", "model": "gpt-4o", "api_key": "sk-realkey123"}
        }
        mgr._loaded = True
        errors = mgr.validate()
        self.assertEqual(errors, [])

    def test_validate_or_raise(self):
        mgr = ConfigManager()
        mgr._config = {"ai_mode": "invalid"}
        mgr._loaded = True
        with self.assertRaises(ConfigValidationError) as ctx:
            mgr.validate_or_raise()
        self.assertGreater(len(ctx.exception.errors), 0)

    def test_invalid_temperature(self):
        mgr = ConfigManager()
        mgr._config = {
            "ai_mode": "local",
            "local": {"base_url": "http://localhost:11434/v1", "model": "test", "temperature": 5.0}
        }
        mgr._loaded = True
        errors = mgr.validate()
        self.assertTrue(any("temperature" in e for e in errors))


class TestConfigManagerActiveMode(unittest.TestCase):
    """活跃模式测试"""

    def test_get_active_mode(self):
        mgr = ConfigManager()
        mgr.reset_to_defaults()
        self.assertEqual(mgr.get_active_mode(), "local")

    def test_get_active_mode_config(self):
        mgr = ConfigManager()
        mgr.reset_to_defaults()
        mode_config = mgr.get_active_mode_config()
        self.assertIn("base_url", mode_config)
        self.assertIn("model", mode_config)


class TestConfigManagerDisplay(unittest.TestCase):
    """展示功能测试"""

    def test_to_display_dict(self):
        mgr = ConfigManager()
        mgr.reset_to_defaults()
        display = mgr.to_display_dict()
        self.assertIn("AI 模式", display)
        self.assertIn("服务地址", display)
        self.assertIn("模型", display)

    def test_display_masks_long_api_key(self):
        mgr = ConfigManager()
        mgr._config = {
            "ai_mode": "cloud",
            "cloud": {"base_url": "https://api.openai.com/v1", "model": "gpt-4o", "api_key": "sk-1234567890abcdef"}
        }
        mgr._loaded = True
        display = mgr.to_display_dict()
        self.assertNotIn("1234567890abcdef", display["API Key"])
        self.assertIn("...", display["API Key"])

    def test_repr(self):
        mgr = ConfigManager()
        mgr.reset_to_defaults()
        # reset_to_defaults 不设置 _loaded，所以显示“未加载”
        self.assertIn("未加载", repr(mgr))
        # 加载后显示模式
        mgr._loaded = True
        self.assertIn("local", repr(mgr))


class TestConfigManagerReset(unittest.TestCase):
    """重置测试"""

    def test_reset_to_defaults(self):
        mgr = ConfigManager()
        mgr._config = {"ai_mode": "cloud"}
        mgr.reset_to_defaults()
        self.assertEqual(mgr.get("ai_mode"), "local")
        self.assertIn("local", mgr.config)
        self.assertIn("cloud", mgr.config)

    def test_config_returns_copy(self):
        """config 属性应返回副本，不影响内部状态"""
        mgr = ConfigManager()
        mgr.reset_to_defaults()
        external = mgr.config
        external["ai_mode"] = "modified"
        self.assertEqual(mgr.get("ai_mode"), "local")


if __name__ == "__main__":
    unittest.main()
