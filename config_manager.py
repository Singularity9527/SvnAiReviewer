"""配置管理模块

统一管理 SVN AI 审查助手的配置文件读写、验证和路径解析。
支持 YAML 格式配置，提供默认配置、多路径查找、配置合并等功能。
"""
import copy
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml

logger = logging.getLogger(__name__)

# 默认配置目录和文件
DEFAULT_CONFIG_DIR = os.path.join(os.path.expanduser("~"), ".svn-ai")
DEFAULT_CONFIG_FILENAME = "config.yaml"
DEFAULT_CONFIG_PATH = os.path.join(DEFAULT_CONFIG_DIR, DEFAULT_CONFIG_FILENAME)

# 默认完整配置
DEFAULT_CONFIG: Dict[str, Any] = {
    "ai_mode": "local",
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


class ConfigError(Exception):
    """配置异常"""
    pass


class ConfigValidationError(ConfigError):
    """配置验证异常"""

    def __init__(self, errors: List[str]):
        self.errors = errors
        super().__init__(f"配置验证失败: {'; '.join(errors)}")


class ConfigManager:
    """配置管理器

    统一管理配置文件的读取、写入、验证和路径查找。

    用法示例::

        # 自动查找配置文件
        mgr = ConfigManager()
        config = mgr.load()

        # 指定路径
        mgr = ConfigManager(config_path="/custom/path/config.yaml")
        config = mgr.load()

        # 修改并保存
        mgr.set("ai_mode", "cloud")
        mgr.set("cloud.api_key", "sk-xxx")
        mgr.save()

        # 获取当前模式配置
        mode_config = mgr.get_active_mode_config()
    """

    # 配置文件搜索路径（优先级从高到低）
    SEARCH_PATHS = [
        lambda: os.path.join(os.getcwd(), DEFAULT_CONFIG_FILENAME),
        lambda: os.path.join(os.getcwd(), ".svn-ai", DEFAULT_CONFIG_FILENAME),
        lambda: DEFAULT_CONFIG_PATH,
    ]

    def __init__(self, config_path: Optional[str] = None):
        """初始化配置管理器

        Args:
            config_path: 指定配置文件路径，None 则自动搜索
        """
        self._config_path = config_path
        self._config: Dict[str, Any] = {}
        self._loaded = False

    @property
    def config_path(self) -> str:
        """当前配置文件路径"""
        if self._config_path:
            return self._config_path
        return DEFAULT_CONFIG_PATH

    @property
    def config(self) -> Dict[str, Any]:
        """当前配置（只读副本）"""
        return copy.deepcopy(self._config)

    @property
    def is_loaded(self) -> bool:
        """配置是否已加载"""
        return self._loaded

    def find_config(self) -> Optional[str]:
        """搜索配置文件

        按优先级从高到低搜索：
        1. 当前目录下的 config.yaml
        2. 当前目录下的 .svn-ai/config.yaml
        3. ~/.svn-ai/config.yaml

        Returns:
            str: 找到的配置文件路径，未找到则返回 None
        """
        if self._config_path:
            if os.path.exists(self._config_path):
                return self._config_path
            return None  # 明确指定路径但不存在，不回退搜索

        for path_fn in self.SEARCH_PATHS:
            path = path_fn()
            if os.path.exists(path):
                logger.debug("找到配置文件: %s", path)
                return path

        return None

    def load(self, use_defaults: bool = False) -> Dict[str, Any]:
        """加载配置

        Args:
            use_defaults: 未找到配置文件时是否使用默认值

        Returns:
            Dict: 配置字典

        Raises:
            ConfigError: 配置文件读取失败
        """
        path = self.find_config()

        if path is None:
            if use_defaults:
                logger.info("未找到配置文件，使用默认配置")
                self._config = copy.deepcopy(DEFAULT_CONFIG)
                self._loaded = True
                return self.config
            raise ConfigError(
                f"未找到配置文件。请运行 'svn-ai config' 创建配置，"
                f"或将 config.yaml 放置在以下位置之一:\n"
                + "\n".join(f"  - {fn()}" for fn in self.SEARCH_PATHS)
            )

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
        except yaml.YAMLError as e:
            raise ConfigError(f"配置文件格式错误 ({path}): {e}")
        except OSError as e:
            raise ConfigError(f"无法读取配置文件 ({path}): {e}")

        if not data or not isinstance(data, dict):
            if use_defaults:
                self._config = copy.deepcopy(DEFAULT_CONFIG)
            else:
                raise ConfigError(f"配置文件为空或格式无效: {path}")
        else:
            self._config = data

        self._config_path = path
        self._loaded = True
        logger.info("加载配置: %s", path)
        return self.config

    def save(self, path: Optional[str] = None) -> str:
        """保存配置到文件

        Args:
            path: 保存路径，None 则使用当前路径或默认路径

        Returns:
            str: 保存的文件路径

        Raises:
            ConfigError: 保存失败
        """
        save_path = path or self._config_path or DEFAULT_CONFIG_PATH

        try:
            os.makedirs(os.path.dirname(save_path), exist_ok=True)
            with open(save_path, "w", encoding="utf-8") as f:
                yaml.dump(
                    self._config,
                    f,
                    default_flow_style=False,
                    allow_unicode=True,
                    sort_keys=False,
                )
        except OSError as e:
            raise ConfigError(f"无法保存配置文件 ({save_path}): {e}")

        self._config_path = save_path
        logger.info("配置已保存: %s", save_path)
        return save_path

    def get(self, key: str, default: Any = None) -> Any:
        """获取配置值（支持点号路径）

        Args:
            key: 配置键，支持 "cloud.api_key" 格式
            default: 默认值

        Returns:
            配置值

        Examples::

            mgr.get("ai_mode")            # "local"
            mgr.get("cloud.api_key")       # "sk-..."
            mgr.get("cloud.timeout", 60)   # 60 (不存在时用默认值)
        """
        keys = key.split(".")
        value = self._config
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default
        return value

    def set(self, key: str, value: Any) -> None:
        """设置配置值（支持点号路径）

        Args:
            key: 配置键，支持 "cloud.api_key" 格式
            value: 配置值

        Examples::

            mgr.set("ai_mode", "cloud")
            mgr.set("cloud.api_key", "sk-xxx")
        """
        keys = key.split(".")
        target = self._config
        for k in keys[:-1]:
            if k not in target or not isinstance(target[k], dict):
                target[k] = {}
            target = target[k]
        target[keys[-1]] = value

    def get_active_mode(self) -> str:
        """获取当前激活的 AI 模式

        Returns:
            str: "local" 或 "cloud"
        """
        return self._config.get("ai_mode", "local")

    def get_active_mode_config(self) -> Dict[str, Any]:
        """获取当前激活模式的配置

        Returns:
            Dict: 当前模式的配置字典
        """
        mode = self.get_active_mode()
        return self._config.get(mode, {})

    def validate(self) -> List[str]:
        """验证当前配置

        Returns:
            List[str]: 错误列表，为空表示验证通过
        """
        errors = []

        # 检查 ai_mode
        ai_mode = self._config.get("ai_mode")
        if not ai_mode:
            errors.append("缺少 'ai_mode' 配置项")
            return errors

        if ai_mode not in ("local", "cloud"):
            errors.append(f"ai_mode 值无效: '{ai_mode}'，应为 'local' 或 'cloud'")
            return errors

        # 检查对应模式的配置
        mode_config = self._config.get(ai_mode)
        if not mode_config or not isinstance(mode_config, dict):
            errors.append(f"缺少 '{ai_mode}' 配置块")
            return errors

        # 检查必填项
        base_url = mode_config.get("base_url", "")
        if not base_url:
            errors.append(f"{ai_mode}.base_url 不能为空")
        elif not base_url.startswith(("http://", "https://")):
            errors.append(f"{ai_mode}.base_url 格式无效: {base_url}")

        model = mode_config.get("model", "")
        if not model:
            errors.append(f"{ai_mode}.model 不能为空")

        # 云端模式需要有效的 API Key
        if ai_mode == "cloud":
            api_key = mode_config.get("api_key", "")
            if not api_key or api_key in ("", "sk-..."):
                errors.append("cloud.api_key 需要设置有效的 API Key")

        # 检查可选数值参数
        for num_key in ("temperature", "max_tokens", "timeout"):
            val = mode_config.get(num_key)
            if val is not None:
                if num_key == "temperature" and not (0 <= val <= 2):
                    errors.append(f"{ai_mode}.temperature 范围应为 0-2，当前值: {val}")
                elif num_key == "max_tokens" and val < 1:
                    errors.append(f"{ai_mode}.max_tokens 应大于 0，当前值: {val}")
                elif num_key == "timeout" and val < 1:
                    errors.append(f"{ai_mode}.timeout 应大于 0，当前值: {val}")

        return errors

    def validate_or_raise(self) -> None:
        """验证配置，失败时抛出异常

        Raises:
            ConfigValidationError: 验证失败
        """
        errors = self.validate()
        if errors:
            raise ConfigValidationError(errors)

    def reset_to_defaults(self) -> None:
        """重置为默认配置"""
        self._config = copy.deepcopy(DEFAULT_CONFIG)
        logger.info("配置已重置为默认值")

    def to_display_dict(self) -> Dict[str, str]:
        """生成用于展示的配置信息（隐藏敏感字段）

        Returns:
            Dict[str, str]: 展示用的键值对
        """
        result = {}
        mode = self.get_active_mode()
        result["AI 模式"] = mode

        mode_config = self.get_active_mode_config()
        result["服务地址"] = mode_config.get("base_url", "未设置")
        result["模型"] = mode_config.get("model", "未设置")

        api_key = mode_config.get("api_key", "")
        if api_key and len(api_key) > 8:
            result["API Key"] = f"{api_key[:4]}...{api_key[-4:]}"
        else:
            result["API Key"] = api_key or "未设置"

        for opt_key in ("temperature", "max_tokens", "timeout"):
            val = mode_config.get(opt_key)
            if val is not None:
                result[opt_key] = str(val)

        return result

    def __repr__(self) -> str:
        mode = self.get_active_mode() if self._loaded else "未加载"
        return f"ConfigManager(path={self._config_path}, mode={mode})"
