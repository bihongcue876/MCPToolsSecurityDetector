# MCP工具安全检测
> Model Context Protocol Tools Security Detector
>
> 基于MCP工具连接而检测部分信息安全专门项的MCP工具安全检测器

## 工具应用
1. 基于MCP的连接，用于MCP工具检测、使用、安全鉴定和模拟攻击（谨慎使用，危险字句应会屏蔽，注入等有关操作仅会探测注入可行性，测试后将复原，并最好发送告知）
2. 主要用于MCP服务器与工具的部分项目安全检查。

## 工具使用
1. 使用压缩包下载：
    - 在一个对应的环境中解压压缩包
    - 运行mcpDetect.exe文件以启动
    - 基于界面使用
2. 使用源码配置：
    - 确保使用环境中配置了python 3.14.4 的环境，在src目录下，基于pip下载有关包（`pip install -r requirements.txt`）
    - 启动src目录下的main.py（使用`python main.py`启动）
    - 基于界面使用

## 说明文档
- 请在仓库中查看使用帮助和服务器启动指南，暂且作为情况与配置说明。
## 其他备注
- 下载
    - 在git仓库的release之中可以下载（至少目前）
- 相关网址
    - GitHub仓库：https://github.com/bihongcue876/MCPToolsSecurityDetector
