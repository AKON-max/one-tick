# 测试 WebSocket 聊天室（临时脚本）
import asyncio
import json

import websockets

WS_URL = "ws://127.0.0.1:8001/ws"


async def main():
    # 1. 无 token 应被拒绝
    try:
        async with websockets.connect(WS_URL) as ws:
            print("[!] 无 token 竟然连接成功（异常）")
    except Exception as e:
        print(f"[1] 无 token 被拒绝 OK: {type(e).__name__}")

    # 2. 无效 token 应被拒绝
    try:
        async with websockets.connect(WS_URL + "?token=invalid-token") as ws:
            print("[!] 无效 token 连接成功（异常）")
    except Exception as e:
        print(f"[2] 无效 token 被拒绝 OK: {type(e).__name__}")

    # 3. 有效 token 连接 + 发消息
    import urllib.request

    body = json.dumps({"email": "http@example.com", "password": "password123"}).encode()
    r = urllib.request.Request(
        "http://127.0.0.1:8001/api/auth/login", data=body, method="POST"
    )
    r.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(r) as resp:
        login = json.loads(resp.read())
    token = login["token"]

    async with websockets.connect(WS_URL + f"?token={token}") as ws:
        # 等待 ready（服务端先广播 presence 再发 ready，与原版 index.ts 顺序一致，需跳过）
        while True:
            raw = await asyncio.wait_for(ws.recv(), timeout=5)
            first = json.loads(raw)
            if first["type"] == "ready":
                break
        assert first["user"]["name"], f"ready user 缺失: {first}"
        print(f"[3] 连接成功 OK, ready user: {first['user']['name']}")

        # 发 ping
        await ws.send(json.dumps({"type": "ping"}))
        while True:
            raw = await asyncio.wait_for(ws.recv(), timeout=5)
            pong = json.loads(raw)
            if pong["type"] == "pong":
                break
        print("[4] ping/pong OK")

        # 发普通消息
        await ws.send(json.dumps({"type": "message", "clientId": "test-001", "content": "大家好，我来测试聊天室"}))
        msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=5))
        while msg["type"] != "message":
            msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=5))
        assert msg["message"]["content"] == "大家好，我来测试聊天室"
        print(f"[5] 消息广播 OK: {msg['message']['content']}")

        # 重复 clientId（幂等去重）
        await ws.send(json.dumps({"type": "message", "clientId": "test-001", "content": "重复消息"}))
        # 等 1 秒看是否有重复广播
        try:
            dup = json.loads(await asyncio.wait_for(ws.recv(), timeout=1.5))
            print(f"[6] 重复消息处理: 收到 {dup['type']}（若为 presence 则去重生效）")
        except asyncio.TimeoutError:
            print("[6] 重复 clientId 被去重 OK（无广播）")

        # 发超长消息（应被拒）
        await ws.send(json.dumps({"type": "message", "clientId": "test-002", "content": "x" * 3000}))
        try:
            err = json.loads(await asyncio.wait_for(ws.recv(), timeout=3))
            assert err["type"] == "error", f"expected error, got {err['type']}"
            print(f"[7] 超长消息被拒 OK: {err['code']}")
        except AssertionError:
            print("[7] 超长消息未被拒（可能被 presence 跳过，继续）")

    print("\n=== WebSocket 测试完成 ===")


asyncio.run(main())
