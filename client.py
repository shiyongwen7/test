import asyncio
import os
import json
from typing import Optional
from dotenv import load_dotenv
from mcp import ClientSession
from openai import OpenAI

# 加载 .env 文件
load_dotenv()


class MCPClient:
    def __init__(self):
        self.openai_api_key = os.getenv("OPENAI_API_KEY")
        self.base_url = os.getenv("BASE_URL")
        self.model = os.getenv("MODEL")
        self.server_url = "http://127.0.0.1:8000/weather"  # 本地 HTTP 工具服务地址

        if not self.openai_api_key:
            raise ValueError("未设置 OPENAI_API_KEY")

        # 初始化大模型客户端
        self.client = OpenAI(api_key=self.openai_api_key, base_url=self.base_url)
        self.session: Optional[ClientSession] = None

    async def initialize_session(self):
        """
        初始化 MCP 会话，模拟工具注册。
        """
        # 模拟工具注册到大模型
        class FakeSession:
            def __init__(self, server_url):
                self.server_url = server_url

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
                """
                调用工具接口，将请求转发给 server 并处理 SSE 数据流。
                """
                import httpx
                print(f"调用工具: {name}, 参数: {args}")  # 调试打印

                # 通用参数映射，将可能的字段名统一映射为服务端需要的字段名
                if 'city_name' in args:
                    args['city'] = args.pop('city_name')
                elif 'location' in args:
                    args['city'] = args.pop('location')

                if 'city' not in args:
                    raise ValueError("工具调用参数中缺少 'city' 字段")

                async with httpx.AsyncClient() as client:
                    # 调用服务端 /weather 接口
                    response = await client.get(self.server_url, params={"city": args['city']}, timeout=30)
                    print(f"服务端响应状态码: {response.status_code}")  # 添加调试日志
                    print(f"服务端响应内容: {response.text}")  # 添加调试日志
                    response.raise_for_status()  # 确保请求成功

                    # 处理 SSE 数据流
                    async for line in response.aiter_lines():
                        if line.startswith("data:"):
                            data = line[5:].strip()  # 去掉 "data:" 前缀
                            if not data:  # 跳过空行
                                continue
                            try:
                                # 尝试解析 JSON 数据
                                parsed_data = json.loads(data)
                                print(f"成功解析的天气数据: {parsed_data}")  # 调试打印
                                return type("Result", (), {
                                    "content": [type("Segment", (), {"text": parsed_data})()]
                                })()
                            except json.JSONDecodeError:
                                print(f"非 JSON 数据，跳过: {data}")  # 调试打印
                                continue

                    raise ValueError("未能从服务端接收到有效的天气数据")

        # 将 server_url 传递给 FakeSession
        self.session = FakeSession(server_url=self.server_url)

    async def process_query(self, query: str) -> str:
        """
        处理用户输入，调用大模型和工具获得最终回复。
        """
        # 将用户输入传递给大模型
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

        # 请求大模型生成带工具调用的回复
        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            tools=available_tools,
        )

        content = response.choices[0]
        if content.finish_reason == "tool_calls":
            # 获取大模型推荐的工具调用信息
            tool_call = content.message.tool_calls[0]
            print(f"大模型工具调用信息: {tool_call}")  # 调试打印
            tool_name = tool_call.function.name
            tool_args = json.loads(tool_call.function.arguments)

            # 调用工具，并获取结果
            result = await self.session.call_tool(tool_name, tool_args)

            # 将工具结果传回大模型
            messages.append(content.message.model_dump())
            messages.append({
                "role": "tool",
                "content": result.content[0].text,
                "tool_call_id": tool_call.id,
            })

            # 请求大模型生成最终回复
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
            )
            return response.choices[0].message.content

        # 如果大模型未调用工具，直接返回回复
        return content.message.content

    async def chat_loop(self):
        """
        客户端交互循环。
        """
        await self.initialize_session()
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