"""
供应商模板配置 (V4.0 全量详实版)

集中管理所有内置的模型供应商模板。
模型列表使用 {"name": ..., "ctx": ..., "type": ...} 格式。
"""

PROVIDER_TEMPLATES = [
    # ========== 1. 硅基流动 (SiliconCloud) - 开源聚合旗舰 ==========
    {
        "name": "SiliconCloud",
        "provider_type": "openai",
        "api_base": "https://api.siliconflow.cn/v1",
        "supported_models": [
            # Chat / Reasoning
            {"name": "deepseek-ai/DeepSeek-V3", "ctx": 64000, "type": "chat"},
            {"name": "deepseek-ai/DeepSeek-R1", "ctx": 64000, "type": "reasoning"},
            {"name": "Pro/deepseek-ai/DeepSeek-V3", "ctx": 128000, "type": "chat"},
            {"name": "Pro/deepseek-ai/DeepSeek-R1", "ctx": 128000, "type": "reasoning"},
            {"name": "Qwen/Qwen2.5-72B-Instruct", "ctx": 32768, "type": "chat"},
            {"name": "Qwen/Qwen2.5-32B-Instruct", "ctx": 32768, "type": "chat"},
            {"name": "Qwen/Qwen2.5-7B-Instruct", "ctx": 32768, "type": "chat"},
            {"name": "Qwen/Qwen2.5-Coder-32B-Instruct", "ctx": 32768, "type": "chat"},
            {"name": "meta-llama/Llama-3.3-70B-Instruct", "ctx": 32768, "type": "chat"},
            {"name": "meta-llama/Llama-3.1-405B-Instruct", "ctx": 32768, "type": "chat"},
            {"name": "THUDM/glm-4-9b-chat", "ctx": 128000, "type": "chat"},
            {"name": "01-ai/Yi-1.5-34B-Chat-16K", "ctx": 16384, "type": "chat"},
            # Embedding
            {"name": "BAAI/bge-m3", "ctx": 8192, "type": "embedding"},
            {"name": "BAAI/bge-large-zh-v1.5", "ctx": 512, "type": "embedding"},
            {"name": "BAAI/bge-large-en-v1.5", "ctx": 512, "type": "embedding"},
            {"name": "nomic-ai/nomic-embed-text-v1.5", "ctx": 8192, "type": "embedding"},
            # Rerank
            {"name": "BAAI/bge-reranker-v2-m3", "ctx": 8192, "type": "rerank"},
            {"name": "BAAI/bge-reranker-v2-gemma-9b", "ctx": 8192, "type": "rerank"},
        ],
        "description": "硅基流动 - 一站式开源大模型平台，涵盖 Llama, Qwen, DeepSeek, GLM 等顶尖开源模型。",
    },

    # ========== 2. 阿里云百炼 (DashScope) - Qwen 官方家族 ==========
    {
        "name": "通义百炼 (DashScope)",
        "provider_type": "openai",
        "api_base": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "supported_models": [
            # Chat
            {"name": "qwen-max", "ctx": 32768, "type": "chat"},
            {"name": "qwen-plus", "ctx": 131072, "type": "chat"},
            {"name": "qwen-turbo", "ctx": 131072, "type": "chat"},
            {"name": "qwen-long", "ctx": 10000000, "type": "chat"},
            {"name": "qwen-vl-max", "ctx": 32768, "type": "vision"}, # 视觉
            {"name": "qwen-vl-plus", "ctx": 32768, "type": "vision"}, # 视觉
            {"name": "qwen2.5-72b-instruct", "ctx": 131072, "type": "chat"},
            # Embedding
            {"name": "text-embedding-v3", "ctx": 8192, "type": "embedding"},
            {"name": "text-embedding-v2", "ctx": 8192, "type": "embedding"},
            # Rerank
            {"name": "gte-rerank", "ctx": 4096, "type": "rerank"},
        ],
        "description": "阿里云官方 API。支持超长文本 Qwen-Long 与视觉多模态 Qwen-VL 系列。",
    },

    # ========== 3. 智谱 AI (BigModel) - GLM 全能系列 ==========
    {
        "name": "智谱 AI (BigModel)",
        "provider_type": "openai",
        "api_base": "https://open.bigmodel.cn/api/paas/v4",
        "supported_models": [
            # Chat
            {"name": "glm-4-plus", "ctx": 128000, "type": "chat"},
            {"name": "glm-4-air", "ctx": 128000, "type": "chat"},
            {"name": "glm-4-long", "ctx": 1024000, "type": "chat"},
            {"name": "glm-4-flash", "ctx": 128000, "type": "chat"},
            {"name": "glm-4v", "ctx": 8192, "type": "vision"}, # 视觉
            {"name": "glm-4-alltools", "ctx": 32768, "type": "chat"},
            {"name": "codegeex-4", "ctx": 128000, "type": "chat"},
            # Embedding
            {"name": "embedding-3", "ctx": 8192, "type": "embedding"},
            {"name": "embedding-2", "ctx": 2048, "type": "embedding"},
        ],
        "description": "智谱清言官方 API。具备国产最强的 GLM-4v 视觉及代码专项模型。",
    },

    # ========== 4. OpenAI - 国际标杆 ==========
    {
        "name": "OpenAI",
        "provider_type": "openai",
        "api_base": "https://api.openai.com/v1",
        "supported_models": [
            # Chat / Reasoning
            {"name": "o1", "ctx": 128000, "type": "reasoning"},
            {"name": "o1-mini", "ctx": 128000, "type": "reasoning"},
            {"name": "o3-mini", "ctx": 128000, "type": "reasoning"},
            {"name": "gpt-4o", "ctx": 128000, "type": "vision"}, # 全模态
            {"name": "gpt-4o-mini", "ctx": 128000, "type": "vision"},
            {"name": "gpt-4-turbo", "ctx": 128000, "type": "vision"},
            {"name": "gpt-3.5-turbo", "ctx": 16385, "type": "chat"},
            # Embedding
            {"name": "text-embedding-3-small", "ctx": 8191, "type": "embedding"},
            {"name": "text-embedding-3-large", "ctx": 8191, "type": "embedding"},
        ],
        "description": "OpenAI 官方通道。支持最新的 o 系列推理与 GPT-4o 视觉模型。",
    },

    # ========== 5. Anthropic (Claude) - 逻辑推理专家 ==========
    {
        "name": "Anthropic (Claude)",
        "provider_type": "anthropic",
        "api_base": "https://api.anthropic.com/v1",
        "supported_models": [
            {"name": "claude-3-5-sonnet-latest", "ctx": 200000, "type": "vision"}, # 视觉支持极佳
            {"name": "claude-3-5-haiku-latest", "ctx": 200000, "type": "chat"},
            {"name": "claude-3-opus-latest", "ctx": 200000, "type": "vision"},
            {"name": "claude-3-sonnet-20240229", "ctx": 200000, "type": "vision"},
            {"name": "claude-3-haiku-20240307", "ctx": 200000, "type": "vision"},
        ],
        "description": "Anthropic 官方 API。Claude 3.5 系列具备顶尖的逻辑与视觉理解力。",
    },

    # ========== 6. Google Gemini - 全模态原生系列 ==========
    {
        "name": "Google Gemini",
        "provider_type": "google",
        "api_base": "https://generativelanguage.googleapis.com/v1beta",
        "supported_models": [
            {"name": "gemini-2.0-flash", "ctx": 1048576, "type": "vision"},
            {"name": "gemini-1.5-pro", "ctx": 2097152, "type": "vision"},
            {"name": "gemini-1.5-flash", "ctx": 1048576, "type": "vision"},
            {"name": "gemini-1.5-flash-8b", "ctx": 1048576, "type": "vision"},
        ],
        "description": "Google API。支持原生百万级超长上下文与极速全模态响应。",
    },

    # ========== 7. 月之暗面 (Moonshot / Kimi) - 中文长文本先行者 ==========
    {
        "name": "Moonshot AI (Kimi)",
        "provider_type": "openai",
        "api_base": "https://api.moonshot.cn/v1",
        "supported_models": [
            {"name": "moonshot-v1-8k", "ctx": 8192, "type": "chat"},
            {"name": "moonshot-v1-32k", "ctx": 32768, "type": "chat"},
            {"name": "moonshot-v1-128k", "ctx": 131072, "type": "chat"},
        ],
        "description": "月之暗面 Kimi 官方接口。以极高水准的中文长文本理解著称。",
    },

    # ========== 8. DeepSeek - 极致性价比推理 ==========
    {
        "name": "DeepSeek (官方)",
        "provider_type": "openai",
        "api_base": "https://api.deepseek.com/v1",
        "supported_models": [
            {"name": "deepseek-chat", "ctx": 65536, "type": "chat"},
            {"name": "deepseek-reasoner", "ctx": 65536, "type": "reasoning"},
        ],
        "description": "深度求索官方接口。提供 V3 对话模型与 R1 推理模型，性价比极致之选。",
    },

    # ========== 9. MiniMax (海螺) - 爆发式垂直能力 ==========
    {
        "name": "MiniMax (海螺)",
        "provider_type": "openai",
        "api_base": "https://api.minimax.chat/v1",
        "supported_models": [
            {"name": "abab6.5s-chat", "ctx": 128000, "type": "chat"},
            {"name": "abab6.5t-chat", "ctx": 8192, "type": "chat"},
            {"name": "abab5.5-chat", "ctx": 32768, "type": "chat"},
        ],
        "description": "MiniMax 官方 API。在角色扮演及语义理解方面具备独特优势。",
    },

    # ========== 10. Groq - 极致推理加速 ==========
    {
        "name": "Groq 推理加速",
        "provider_type": "openai",
        "api_base": "https://api.groq.com/openai/v1",
        "supported_models": [
            {"name": "llama-3.3-70b-versatile", "ctx": 128000, "type": "chat"},
            {"name": "llama-3.1-70b-versatile", "ctx": 131072, "type": "chat"},
            {"name": "mixtral-8x7b-32768", "ctx": 32768, "type": "chat"},
            {"name": "gemma2-9b-it", "ctx": 8192, "type": "chat"},
        ],
        "description": "Groq LPU 加速平台。提供秒级响应，托管 Llama, Mixtral 等模型。",
    },

    # ========== 11. OpenRouter - 全球模型枢纽 ==========
    {
        "name": "OpenRouter",
        "provider_type": "openai",
        "api_base": "https://openrouter.ai/api/v1",
        "supported_models": [
            {"name": "anthropic/claude-3.5-sonnet", "ctx": 200000, "type": "vision"},
            {"name": "openai/gpt-4o", "ctx": 128000, "type": "vision"},
            {"name": "google/gemini-pro-1.5", "ctx": 1000000, "type": "vision"},
            {"name": "meta-llama/llama-3.3-70b-instruct", "ctx": 128000, "type": "chat"},
        ],
        "description": "全能模型聚合网关，支持调用海外几乎所有顶尖商业及开源大模型。",
    },
]
