import json
import re

def clean_json(text: str) -> str:
    """
    清洗 LLM 返回的 JSON 字符串。
    移除 markdown 代码块标记和其他干扰字符。
    """
    # 移除 markdown 代码块
    text = re.sub(r'```json\s*', '', text)
    text = re.sub(r'```\s*', '', text)
    
    # 移除前后空白
    text = text.strip()
    
    return text
