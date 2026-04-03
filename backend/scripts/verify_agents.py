import sys, os; sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import httpx
import json

BASE_URL = "http://localhost:8000/v1"
HEADERS = {
    "Content-Type": "application/json",
    "X-Session-Id": "demo-session-123",
    "X-Enable-Memory": "true"
}

def test_agent(agent_id, query):
    print(f"\n--- 🤖 Testing Agent: {agent_id} ---")
    data = {
        "model": agent_id,
        "messages": [
            {"role": "user", "content": query}
        ],
        "stream": False
    }
    
    try:
        response = httpx.post(f"{BASE_URL}/chat/completions", json=data, headers=HEADERS, timeout=30.0)
        if response.status_code == 200:
            result = response.json()
            content = result['choices'][0]['message']['content']
            print(f"Assistant: {content}")
        else:
            print(f"❌ Error {response.status_code}: {response.text}")
    except Exception as e:
        print(f"❌ Connection failed: {e}")

if __name__ == "__main__":
    print("UniAI Agent Platform - Integration Test")
    
    # 场景 1: 调用翻译官 (即使提问很啰嗦，它也应该只输出英文翻译)
    test_agent("agent-translator", "你好，请问今天天气怎么样？我希望你能帮我翻译这句话。")
    
    # 场景 2: 调用联网研究员 (它应该尝试调用工具或展现出研究员的人设)
    test_agent("agent-researcher", "请帮我搜索并分析一下 2024 年人工智能领域最值得关注的三个突破是什么？")
    
    # 场景 3: 默认兜底 (如果在数据库找不到该 ID，会回退到 .env 的默认模型)
    test_agent("qwen-flash", "你是谁？")
