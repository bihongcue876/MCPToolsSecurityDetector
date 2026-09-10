# stdio
from fastmcp import FastMCP

# test 1 text, 4 calculate

mcp = FastMCP("Default Simple Server STDIO")

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

def default_calculate_stdio_run():
    mcp.run()

if __name__ == "__main__":
    default_calculate_stdio_run()  # 默认 stdio
    
"""
注：stdio基于本地进程管理，如果基于fastmcp环境参数调用，则可以直接访问。
1. 启动：运行，即python default_calculate_stdio.py
2. 工具列表：fastmcp list default_calculate_stdio.py
3. 工具调用：fastmcp call default_calculate_stdio.py [toolname] arg1=... arg2=... ......
   例：fastmcp call default_calculate_stdio.py add a=3 b=5
"""
