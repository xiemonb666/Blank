#!/usr/bin/env python3
"""
V2 SSE 流式接口端到端测试脚本
==============================
用途：验证 /api/v2/chat/stream 接口的 SSE 流式输出是否正常。

运行方式：
    cd backend
    python -m app.test_v2_chat_endpoint

说明：
    脚本会自动登录测试账号，获取 session 列表后调用 V2 流式接口，
    并在终端实时打印接收到的 SSE 事件。
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import httpx

API_BASE = "http://127.0.0.1:8000"
TEST_USERNAME = "v2_test_user"
TEST_PASSWORD = "Passw0rd123"


def _login() -> httpx.Cookies:
    """自动注册/登录，返回带认证 Cookie 的客户端。"""
    client = httpx.Client(base_url=API_BASE, timeout=30)

    # 尝试登录
    resp = client.post(
        "/api/auth/login",
        headers={"Origin": "http://127.0.0.1:5173", "Content-Type": "application/json"},
        json={"username": TEST_USERNAME, "password": TEST_PASSWORD},
    )
    if resp.status_code == 401:
        # 用户不存在，先注册
        print(f"[信息] 用户 {TEST_USERNAME} 不存在，自动注册...")
        reg = client.post(
            "/api/auth/register",
            headers={"Origin": "http://127.0.0.1:5173", "Content-Type": "application/json"},
            json={"username": TEST_USERNAME, "password": TEST_PASSWORD},
        )
        if reg.status_code != 200:
            print(f"[错误] 注册失败：{reg.status_code} {reg.text}")
            sys.exit(1)
        # 重新登录
        resp = client.post(
            "/api/auth/login",
            headers={"Origin": "http://127.0.0.1:5173", "Content-Type": "application/json"},
            json={"username": TEST_USERNAME, "password": TEST_PASSWORD},
        )

    if resp.status_code != 200:
        print(f"[错误] 登录失败：{resp.status_code} {resp.text}")
        sys.exit(1)

    print(f"[信息] 登录成功：{TEST_USERNAME}")
    return client


def _get_or_create_session(client: httpx.Client) -> str:
    """获取一个现有 session ID，如果没有则创建。"""
    resp = client.get("/api/sessions")
    if resp.status_code == 200:
        sessions = resp.json()
        if sessions:
            sid = sessions[0]["id"]
            print(f"[信息] 使用已有 session：{sid}")
            return sid

    # 创建新 session
    print("[信息] 没有现有 session，正在创建...")
    resp = client.post(
        "/api/sessions",
        headers={"Content-Type": "application/json"},
        json={
            "title": "V2 测试材料",
            "content": "计算机网络中的 TCP 协议。TCP 通过三次握手建立连接，通过四次挥手断开连接。",
        },
    )
    if resp.status_code != 200:
        print(f"[错误] 创建 session 失败：{resp.status_code} {resp.text}")
        sys.exit(1)

    sid = resp.json()["session"]["id"]
    print(f"[信息] 创建 session 成功：{sid}")
    return sid


def _stream_chat(session_id: str, message: str, persona: str = "plain") -> None:
    """调用 V2 SSE 流式接口，并实时打印事件。"""
    client = _login()

    # 先确保有 session
    _get_or_create_session(client)

    print(f"\n[请求] POST /api/v2/chat/stream")
    print(f"       session_id={session_id}, message='{message}', persona={persona}")
    print("-" * 60)

    # SSE 流式请求：使用 stream=True 逐行读取
    with client.stream(
        "POST",
        "/api/v2/chat/stream",
        headers={
            "Origin": "http://127.0.0.1:5173",
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
        },
        json={"session_id": session_id, "message": message, "persona": persona},
    ) as response:
        if response.status_code != 200:
            print(f"[错误] 请求失败：{response.status_code}")
            print(response.text())
            return

        for line in response.iter_lines():
            if not line:
                continue
            text = line.decode("utf-8") if isinstance(line, bytes) else line
            if not text.startswith("data: "):
                continue
            payload = text.removeprefix("data: ").strip()
            try:
                event = json.loads(payload)
            except json.JSONDecodeError:
                continue

            etype = event.get("type", "unknown")
            if etype == "status":
                print(f"  [状态] {event.get('agent', '')}: {event.get('message', '')}")
            elif etype == "thought":
                print(f"  [思考] {event.get('content', '')[:120]}...")
            elif etype == "message":
                print(f"  [消息] {event.get('content', '')}", end="")
            elif etype == "feynman_result":
                data = event.get("data", {})
                passed = data.get("overall_passed", False)
                print(f"\n  [费曼] 通过={passed} | 维度数={len(data.get('dimension_scores', []))}")
            elif etype == "done":
                print("\n  [结束] SSE 流已关闭")
                break
            elif etype == "error":
                print(f"\n  [错误] {event.get('error', '')}")

    print("-" * 60)
    client.close()


def main() -> int:
    print("=" * 60)
    print("Blank V2 SSE 流式接口端到端测试")
    print("=" * 60)

    # 用例 1：学习者提问
    _stream_chat(
        session_id="test-session-v2-001",
        message="为什么TCP断开连接需要四次挥手而不是三次？",
        persona="plain",
    )

    # 用例 2：费曼复述
    _stream_chat(
        session_id="test-session-v2-001",
        message="我的理解是，TCP通过三次握手建立连接，四次挥手断开，因为全双工需要分别关闭两个方向。",
        persona="academic",
    )

    print("\n" + "=" * 60)
    print("测试完成。")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
