import json
import httpx
from typing import Any
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sse_starlette.sse import EventSourceResponse

app = FastAPI()

# CORS 设置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 允许所有来源
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# OpenWeather API 配置
OPENWEATHER_API_BASE = "https://api.openweathermap.org/data/2.5/weather"
API_KEY = "15e642fb1dba697034ca7b888c420247"  # 请替换为你自己的 OpenWeather API Key
USER_AGENT = "weather-app/1.0"


async def fetch_weather(city: str) -> dict[str, Any] | None:
    """
    从 OpenWeather API 获取天气信息。
    """
    params = {
        "q": city,
        "appid": API_KEY,
        "units": "metric",
        "lang": "zh_cn"
    }
    headers = {"User-Agent": USER_AGENT}
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(OPENWEATHER_API_BASE, params=params,
                                        headers=headers, timeout=30.0)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            print(f"HTTP 错误: {e.response.status_code}")  # 调试日志
            return {"error": f"HTTP 错误: {e.response.status_code}"}
        except Exception as e:
            print(f"请求失败: {str(e)}")  # 调试日志
            return {"error": f"请求失败: {str(e)}"}


@app.get("/weather")
async def get_weather(city: str):
    """
    SSE 端点：接受城市名称并返回天气数据。
    """
    print(f"接收到的参数: city={city}")  # 添加调试日志
    async def weather_stream():
        yield "data: 正在获取天气信息...\n\n"
        weather_data = await fetch_weather(city)
        print(f"天气数据: {weather_data}")  # 添加调试日志
        yield f"data: {json.dumps(weather_data)}\n\n"

    return EventSourceResponse(weather_stream())