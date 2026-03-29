"""
供应商模板配置

集中管理所有内置的模型供应商模板。
"""

PROVIDER_TEMPLATES = [
    # ========== 免费/试用模型 ==========
    {
        "name": "DeepSeek",
        "provider_type": "openai",
        "api_base": "https://api.deepseek.com/v1",
        "is_free": True,
        "requires_api_key": True,
        "supported_models": ["deepseek-chat", "deepseek-coder"],
        "description": "DeepSeek 开源模型，提供免费 API 额度",
        "config_schema": {
            "api_key": {"required": True, "description": "DeepSeek API Key (platform.deepseek.com)"}
        }
    },
    {
        "name": "Groq",
        "provider_type": "openai",
        "api_base": "https://api.groq.com/openai/v1",
        "is_free": True,
        "requires_api_key": True,
        "supported_models": ["llama-3.1-70b-versatile", "mixtral-8x7b-32768", "llama-3.2-90b-vision-preview"],
        "description": "Groq 超快推理，免费额度 (console.groq.com)",
        "config_schema": {
            "api_key": {"required": True, "description": "Groq API Key"}
        }
    },
    {
        "name": "智谱AI",
        "provider_type": "openai",
        "api_base": "https://open.bigmodel.cn/api/paas/v4",
        "is_free": True,
        "requires_api_key": True,
        "supported_models": ["glm-4", "glm-4-flash", "glm-4-plus"],
        "description": "智谱 GLM-4，每月免费额度 (open.bigmodel.cn)",
        "config_schema": {
            "api_key": {"required": True, "description": "智谱 API Key"}
        }
    },
    {
        "name": "通义千问",
        "provider_type": "openai",
        "api_base": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "is_free": True,
        "requires_api_key": True,
        "supported_models": ["qwen-turbo", "qwen-plus", "qwen-max", "qwen-flash"],
        "description": "阿里云通义千问，免费试用额度 (dashscope.aliyuncs.com)",
        "config_schema": {
            "api_key": {"required": True, "description": "通义千问 API Key"}
        }
    },
    
    # ========== 付费主流模型 ==========
    {
        "name": "OpenAI",
        "provider_type": "openai",
        "api_base": "https://api.openai.com/v1",
        "is_free": False,
        "requires_api_key": True,
        "supported_models": [
            "gpt-4-turbo", "gpt-4", "gpt-3.5-turbo",
            "text-embedding-3-small", "text-embedding-3-large"
        ],
        "description": "OpenAI 官方 API (platform.openai.com)",
        "config_schema": {
            "api_key": {"required": True, "description": "OpenAI API Key"}
        }
    },
    {
        "name": "Anthropic",
        "provider_type": "anthropic",
        "api_base": "https://api.anthropic.com",
        "is_free": False,
        "requires_api_key": True,
        "supported_models": [
            "claude-3-opus-20240229",
            "claude-3-sonnet-20240229",
            "claude-3-haiku-20240307"
        ],
        "description": "Anthropic Claude 系列 (console.anthropic.com)",
        "config_schema": {
            "api_key": {"required": True, "description": "Anthropic API Key"}
        }
    },
    {
        "name": "Google Gemini",
        "provider_type": "gemini",
        "api_base": "https://generativelanguage.googleapis.com/v1beta",
        "is_free": False,
        "requires_api_key": True,
        "supported_models": ["gemini-pro", "gemini-pro-vision", "gemini-1.5-pro"],
        "description": "Google Gemini API (ai.google.dev)",
        "config_schema": {
            "api_key": {"required": True, "description": "Google API Key"}
        }
    },
]
