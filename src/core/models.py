# 数据结构与数据模型
from dataclasses import dataclass, field # 解释数据结构用，field用于控制属性
from typing import Any
from datetime import datetime # 时间戳
import uuid

# MCP服务器配置
@dataclass
class ServerConfig: 
    _id : str # 唯一表示（uuid）
    name : str # 用户显示定义名
    transport : str # "stdio" | "sse" | "http"
    command : str = "" # stdio 默认指令
    args : list = field(default_factory=list) # args stdio
    env : dict = field(default_factory=dict) # env stdio
    url : str = "" # http/sse url
    headers : dict = field(default_factory=dict) # 额外请求头 requests head
    auth_type : str = "none" # 鉴权 none / bearer / api_key
    auth_value : str = "" # 凭证内容，此处暂时采用明文方式
    timeout : int = 10 # 连接超时时间
    create_at : str = "" # ISO time scrap
    update_at : str = "" # ISO time scrap
    
# 工具信息
@dataclass
class ToolInfo:
    name: str
    description: str
    input_schema: dict # 原始 JSON Schema
    annotations: dict = field(default_factory=dict) # 如 readOnlyHint, destructiveHint
    
# 检测结论
@dataclass
class DetectionResult:
    module: str # 项目分类号，"A"、"B"等
    item_id: str # 项目编号，如 "A1"
    item_name: str # 检测项名称
    status: str # 检测状态，"pass" | "warn" | "fail"
    # severity: str # 严重程度，"high" | "medium" | "low" | "info"，当需要时取消注释
    evidence: str # 证据文本（原样片段或描述）
    suggestion: str # 情况描述（存在的问题与修复的方向）

# 进攻模拟数据
@dataclass
class AttackPayload:
    id: str # 编号或uuid
    name: str # 显示名称，如“忽略指令”
    category: str # 类别：prompt_injection, path_traversal, command_injection等
    payload: str # 实际注入工具的文本
    description: str # 用途说明
    is_builtin: bool = False # 是否为固有数据（是则不予删除）

# 工具使用记录
@dataclass
class ToolCallRecord:
    id: int = 0 # 记录编号，插入前为0
    server_id: str = ""
    tool_name: str = ""
    args_json: str = "" # 工具调用参数
    response_json: str = "" # 工具调用结论
    is_attack: bool = False # 是否为攻击模拟，默认非
    payload_id: str = "" # 若为攻击，记录载荷ID
    timestamp: str = ""
    
# 检测记录
@dataclass
class DetectionRun:
    id: int = 0
    server_id: str = ""
    server_name: str = ""
    run_time: str = ""
    results: list = field(default_factory=list)  # list[DetectionResult]