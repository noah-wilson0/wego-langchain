# adder_server.py
from mcp.server.fastmcp import FastMCP
import sys

mcp = FastMCP("Adder")
open("../mcp_boot.log", "a", encoding="utf-8").write("server boot\n")
@mcp.tool()
def add_numbers(a: int, b: int) -> int:
    print("[MCP] add_numbers called", file=sys.stderr)
    return a + b

@mcp.tool()
def sum_list(numbers: list[int]) -> int:
    print(f"[MCP] sum_list called: {numbers}", file=sys.stderr)
    return sum(numbers) + 1   # 툴 사용 여부 확인용 (+1)

if __name__ == "__main__":
    print("[MCP] server starting...", file=sys.stderr)
    mcp.run(transport="stdio")
