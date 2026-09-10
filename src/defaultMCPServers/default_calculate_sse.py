# sse server （已经废弃，现在不采用这种方式，仅应用）
from fastmcp import FastMCP

# test 1 text, 4 calculate

mcp = FastMCP("Default Simple Server HTTP")

@mcp.tool()
def echo(text: str) -> str:
    """返回默认文字"""
    return text

@mcp.tool()
def add(a: float, b: float) -> float:
    """两数相加"""
    return a + b

@mcp.tool()
def sub(a: float, b: float) -> float:
    """两数相减"""
    return a - b

@mcp.tool()
def mul(a: float, b: float) -> float:
    """两数相乘"""
    return a * b

@mcp.tool()
def div(a: float, b: float) -> str:
    """两数相除，除0警告"""
    if b == 0:
        return "Warning: division by zero is undefined"
    return str(a / b)

def default_calculate_sse_run():
    mcp.run(transport="sse", host="127.0.0.1", port=7654)

if __name__ == "__main__":
    default_calculate_sse_run()  # 默认 sse http://localhost:7654/sse
    
"""
注：运行本文件则启动MCP服务器。
1. 默认端口 http://localhost:7654/sse
"""

