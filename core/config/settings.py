# core/config/settings.py
import os
import tomli
from functools import lru_cache
from pathlib import Path
from typing import Any
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings


class LogConfig(BaseModel):
    """日志配置"""
    level: str = Field(default="INFO")
    dir: str = Field(default="./logs")
    rotation: str = Field(default="100 MB")
    retention: str = Field(default="10 days")
    api_log_enabled: bool = Field(default=True, description="Whether to enable API request logging")

class AppConfig(BaseModel):
    """主应用配置"""
    service_name: str = Field(default="km_portal-service")
    service_version: str = Field(default="1.0.0")
    title: str = Field(default="KM Portal")
    description: str = Field(default="KM Portal Background Service")
    debug: bool = Field(default=False)
    upload_workers: int = Field(default=2, ge=1, le=20)
    km_db_check_interval: int = Field(default=60, ge=1, le=65536)
    log: LogConfig = LogConfig()

class KBotConfig(BaseModel):
    """KBot 配置"""
    app_id: int = Field(default=1, description="Unique application identifier")
    domain_id: int = Field(default=1, description="Unique domain identifier")
    kb_id: int = Field(default=1, description="Unique knowledge base identifier")
    upload_api_url: str = Field(default="http://localhost:18090/api/kb/upload", description="KBot upload API URL")

class Settings(BaseSettings):
    """全局配置设置"""
    
    # 环境配置 - 支持环境变量覆盖
    environment: str = "development"
    config_dir: str = "../configuration"
    
    # 各模块配置
    app: AppConfig = AppConfig()
    kbot: KBotConfig = KBotConfig()
    
    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8", 
        "case_sensitive": False,
        "extra": "ignore",
        "env_prefix": "",  # 环境变量不需要前缀
    }
    
    @classmethod
    def create(cls, toml_path: Path | None = None) -> "Settings":
        """创建配置实例 - 支持环境变量切换"""
        # 首先检查环境变量
        env_from_env = os.getenv("ENVIRONMENT")
        config_dir_from_env = os.getenv("CONFIG_DIR")
        
        # 创建临时实例来获取其他配置
        temp_settings = cls()
        
        # 确定环境：环境变量优先，然后是配置文件
        environment = env_from_env or temp_settings.environment
        config_dir = Path(config_dir_from_env or temp_settings.config_dir)
        
        print(f"Loading configuration for environment: {environment}")
        print(f"Config directory: {config_dir}")
        
        if toml_path is None:
            toml_path = config_dir / f"{environment}.toml"
            print(f"Loading TOML from: {toml_path}")
        
        # 确保配置目录存在
        config_dir.mkdir(parents=True, exist_ok=True)
        
        # 加载基础配置
        base_config_path = config_dir / "base.toml"
        base_config = cls._load_toml(base_config_path)
        
        # 加载环境特定配置
        env_config = cls._load_toml(toml_path)
        
        # 合并配置
        merged_config = cls._deep_merge(base_config, env_config)
        
        # 创建最终配置实例
        final_settings = cls(**merged_config)
        
        # 确保环境设置正确（环境变量可能覆盖了配置文件）
        if env_from_env:
            final_settings.environment = env_from_env
        if config_dir_from_env:
            final_settings.config_dir = config_dir_from_env
            
        return final_settings
    
    @staticmethod
    def _load_toml(file_path: Path) -> dict[str, Any]:
        """加载 TOML 文件，如果文件不存在返回空字典"""
        if not file_path.exists():
            print(f"Warning: Config file {file_path} not found, using defaults")
            return {}
        
        try:
            with open(file_path, "rb") as f:
                config = tomli.load(f)
                print(f"Loaded TOML config from: {file_path}")
                return config
        except Exception as e:
            print(f"Error loading TOML config {file_path}: {e}, using defaults")
            return {}
    
    @staticmethod
    def _deep_merge(base: dict, update: dict) -> dict:
        """深度合并字典"""
        result = base.copy()
        
        for key, value in update.items():
            if (key in result and isinstance(result[key], dict) 
                and isinstance(value, dict)):
                result[key] = Settings._deep_merge(result[key], value)
            else:
                result[key] = value
                
        return result

    def is_development(self) -> bool:
        """检查是否为开发环境"""
        return self.environment.lower() in ["dev", "development", "debug"]
    
    def is_production(self) -> bool:
        """检查是否为生产环境"""
        return self.environment.lower() in ["prod", "production", "live"]
    
    def is_testing(self) -> bool:
        """检查是否为测试环境"""
        return self.environment.lower() in ["test", "testing", "staging"]


# 全局配置实例
@lru_cache()
def get_settings() -> Settings:
    """获取缓存的配置实例"""
    return Settings.create()

# 便捷访问函数
def get_app_config() -> AppConfig:
    """获取主应用配置"""
    return get_settings().app

def get_log_config() -> LogConfig:
    """获取日志配置"""
    return get_settings().app.log

def get_kbot_config() -> KBotConfig:
    """获取 KBot 配置"""
    return get_settings().kbot
