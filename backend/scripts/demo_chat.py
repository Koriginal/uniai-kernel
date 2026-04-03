import sys, os; sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import httpx
import json
import asyncio

async def chat_with_agent(agent_id: str, query: str, stream: bool = True):
    """
    演示如何与 Agent 对话。
    """
    # 使用业务侧专用接口
    url = f"http://localhost:8000/api/v1/agents/{agent_id}/chat"
    headers = {
        "Content-Type": "application/json"
    }
    
    payload = {
        "query": query,
        "stream": stream,
        "session_id": "demo-session-456"
    }

    print(f"\n--- [Requesting Agent: {agent_id}] ---")
    print(f"User: {query}\n")

    if stream:
        async with httpx.AsyncClient(timeout=60.0) as client:
            async with client.stream("POST", url, headers=headers, json=payload) as response:
                if response.status_code != 200:
                    print(f"Error: {response.status_code}")
                    return
                
                print("Assistant: ", end="", flush=True)
                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        data_str = line[6:]
                        if data_str == "[DONE]":
                            break
                        try:
                            data = json.loads(data_str)
                            content = data["choices"][0]["delta"].get("content", "")
                            print(content, end="", flush=True)
                        except:
                            continue
                print("\n")
    else:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(url, headers=headers, json=payload)
            if response.status_code == 200:
                result = response.json()
                content = result["choices"][0]["message"]["content"]
                print(f"Assistant: {content}\n")
            else:
                print(f"Error: {response.status_code}, {response.text}")

async def main():
    # 演示 1：调用中英翻译官 (agent-translator)
    await chat_with_agent("agent-translator", "Hello, how are you today?")
    
    # 演示 2：调用联网研究员 (agent-researcher)
    await chat_with_agent("agent-researcher", "搜索并总结一下 2024 年最热门的 AI 技术趋势。")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
