# llm.py
import os, sys
from pathlib import Path
from dotenv import load_dotenv

from langchain_mcp_adapters.client import MultiServerMCPClient
from langgraph.prebuilt import create_react_agent
from langchain_google_genai import ChatGoogleGenerativeAI

load_dotenv()

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
if not GOOGLE_API_KEY:
    raise RuntimeError("환경변수 GOOGLE_API_KEY 없음")

def _resolve_mcp_server_script() -> str:
    override = os.getenv("WEGO_MCP_SERVER")
    if override:
        p = Path(override).expanduser().resolve()
        if p.exists():
            return str(p)
        raise RuntimeError(f"WEGO_MCP_SERVER 경로가 존재하지 않습니다: {p}")

    here = Path(__file__).resolve().parent
    c = here / "wego_mcp_server.py"  # <-- 같은 폴더
    if c.exists():
        print(f"[llm] MCP server: {c}", file=sys.stderr, flush=True)
        return str(c)

    raise RuntimeError(f"MCP server not found next to llm.py: {c}")

SERVER_SCRIPT = _resolve_mcp_server_script()

# def make_llm():
    # return ChatGoogleGenerativeAI(model="gemini-2.0-flash", api_key=GOOGLE_API_KEY )
def make_llm():
    return ChatGoogleGenerativeAI(model="gemini-2.5-flash", api_key=GOOGLE_API_KEY,
                                  generation_config={
                                      "response_mime_type": "application/json",
                                      "temperature": 0,
                                  },
                                  )

# def make_llm():
#     return ChatGoogleGenerativeAI(model="gemini-2.5-flash", api_key=GOOGLE_API_KEY,
#                                   generation_config={
#                                       "response_mime_type": "application/json",  # ✅ JSON만 내게 강제
#                                       "max_output_tokens": 4096,
#                                       "temperature": 0.6,
#                                   },
#                                   )

async def make_mcp_client():
    spring_base = os.getenv("SPRING_BASE", "http://localhost:8080")
    return MultiServerMCPClient({
        "wego": {
            "command": sys.executable,
            "args": ["-u", SERVER_SCRIPT],
            "transport": "stdio",
            "env": {
                "PYTHONUNBUFFERED": "1",
                "PYTHONIOENCODING": "utf-8",
                "SPRING_BASE": spring_base,
            },
        }
    })

def make_agent(llm, tools, system_prompt: str):
    return create_react_agent(llm, tools, prompt=system_prompt)
