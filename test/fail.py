# fail.py
"""
mcp 테스트중 안됫었던 코드
이유는 모름
"""
import asyncio, os, sys
from pathlib import Path
from dotenv import load_dotenv

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_mcp_adapters.tools import load_mcp_tools  # README 스타일 임포트

from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.messages import HumanMessage
from langchain.agents import create_tool_calling_agent, AgentExecutor

# 1) 환경 변수
load_dotenv()
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
assert GOOGLE_API_KEY, "GOOGLE_API_KEY 가 .env 에 필요합니다."

# 2) 모델
llm = ChatGoogleGenerativeAI(
    model="gemini-2.0-flash",
    api_key=GOOGLE_API_KEY,
)

# 3) 서버 경로
PROJECT_DIR = Path(__file__).resolve().parent
SERVER_PATH = str((PROJECT_DIR / "adder_server.py").resolve())

async def main():
    # 4) MCP 툴 로드 (README 방식: servers=...)
    tools = await load_mcp_tools(
        servers={
            "adder": {
                "type": "stdio",
                "command": sys.executable,          # 현재 venv 파이썬
                "args": ["-u", SERVER_PATH],        # -u: stdio 언버퍼
                "cwd": str(PROJECT_DIR),
                "env": {
                    "PYTHONUNBUFFERED": "1",
                    "PYTHONIOENCODING": "utf-8",
                },
            }
        }
    )

    print("== Available MCP Tools ==")
    for t in tools:
        print("-", t.name)

    # (선택) 직접 호출로 툴 연결 확인: 101이 나오면 OK
    tmap = {t.name: t for t in tools}
    if "sum_list" in tmap:
        res = await tmap["sum_list"].ainvoke({"numbers": [12, 30, 7, 51]})
        print("== Direct MCP call (should be 101) ==", res)

    # 5) Agent 프롬프트 (README 스타일)
    prompt = ChatPromptTemplate.from_messages([
        ("system",
         "You are a helpful assistant. "
         "You MUST use available tools for arithmetic. "
         "Never print code blocks; call tools instead."),
        MessagesPlaceholder("chat_history"),
        ("human", "{input}"),
        MessagesPlaceholder("agent_scratchpad"),
    ])

    # 6) Agent 생성 및 실행기
    agent = create_tool_calling_agent(llm, tools, prompt)
    agent_executor = AgentExecutor(agent=agent, tools=tools, verbose=True)

    # 7) 실행 (자연어 → 에이전트가 자동으로 MCP 툴 호출)
    result = await agent_executor.ainvoke({
        "input": "MCP 도구만 사용해서 12, 30, 7, 51의 합계를 계산하고, 결과 숫자만 출력해."
    })

    print("\n=== Final ===")
    print(result["output"])

if __name__ == "__main__":
    asyncio.run(main())
