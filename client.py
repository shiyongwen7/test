# client.py
import asyncio
import os
import json
import sys
from typing import Optional
from contextlib import AsyncExitStack
from openai import OpenAI
from dotenv import load_dotenv
from mcp import ClientSession

# 加载 .env 文件
load_dotenv()

class MCPClient:
    def __init__(self):
        self.exit_stack = AsyncExitStack()
        self.openai_api_key = os.getenv("OPENAI_API_KEY")
        self.base_url = os.getenv("BASE_URL")
        self.model = os.getenv("MODEL")
        self.server_url = "http://127.0.0.1:9000"  # 本地 HTTP 工具服务地址

        if not self.openai_api_key:
            raise ValueError("未设置 OPENAI_API_KEY")

        self.client = OpenAI(api_key=self.openai_api_key, base_url=self.base_url)
        self.session: Optional[ClientSession] = None

    async def initialize(self):
        # 提前保存 server_url 供 FakeSession 使用
        server_url = self.server_url

        # 模拟远程工具注册
        class FakeSession:
            async def list_tools(self):
                return type("Resp", (), {
                    "tools": [
                        type("Tool", (), {
                            "name": "query_weather",
                            "description": "根据城市英文名查询天气。例如：Beijing 表示北京，Shanghai 表示上海。",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "city": {
                                        "type": "string",
                                        "description": "城市名称（英文，如 Beijing 表示北京）"
                                    }
                                },
                                "required": ["city"]
                            }
                        })()
                    ]
                })()


            async def call_tool(self, name: str, args: dict):
                import httpx
                async with httpx.AsyncClient() as client:
                    resp = await client.post(f"{server_url}/tools/{name}", json=args, timeout=30)
                    resp.raise_for_status()
                    return type("Result", (), {
                        "content": [type("Segment", (), {"text": resp.json()["text"]})()]
                    })()

        self.session = FakeSession()

    async def process_query(self, query: str) -> str:
        messages = [{"role": "user", "content": query}]
        response = await self.session.list_tools()
        available_tools = [{
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "input_schema": tool.inputSchema
            }
        } for tool in response.tools]

        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            tools=available_tools
        )

        content = response.choices[0]
        if content.finish_reason == "tool_calls":
            tool_call = content.message.tool_calls[0]
            tool_name = tool_call.function.name
            tool_args = json.loads(tool_call.function.arguments)
            result = await self.session.call_tool(tool_name, tool_args)
            messages.append(content.message.model_dump())
            messages.append({
                "role": "tool",
                "content": result.content[0].text,
                "tool_call_id": tool_call.id,
            })

            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
            )
            return response.choices[0].message.content

        return content.message.content

    async def chat_loop(self):
        await self.initialize()
        print("\n🧠 MCP 客户端已启动，输入 'quit' 退出\n")
        while True:
            try:
                query = input("你: ").strip()
                if query.lower() == 'quit':
                    break
                response = await self.process_query(query)
                print(f"\n🤖 大模型回复: {response}")
            except Exception as e:
                print(f"\n❌ 发生错误: {str(e)}")

async def main():
    client = MCPClient()
    await client.chat_loop()

if __name__ == "__main__":
    asyncio.run(main())
