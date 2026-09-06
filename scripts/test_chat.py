# 测试聊天室（临时脚本）
import json
import urllib.request

BASE = "http://127.0.0.1:8001"


def req(method, path, token=None, body=None):
    data = json.dumps(body).encode() if body else None
    r = urllib.request.Request(BASE + path, data=data, method=method)
    r.add_header("Content-Type", "application/json")
    if token:
        r.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(r) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


# 登录
code, login = req("POST", "/api/auth/login", body={"email": "http@example.com", "password": "password123"})
assert code == 200, f"login failed: {code}"
token = login["token"]
print("[1] 登录 OK")

# 聊天记录（应有之前测试会话的消息? 无，但应有空数组或已有内容）
code, data = req("GET", "/api/chat/messages", token)
assert code == 200, f"chat messages failed: {code}"
print(f"[2] 聊天记录 OK: {len(data['messages'])} 条")

print("\n=== 聊天记录 API 测试通过 ===")
print("（WebSocket 握手/心跳/广播用 Python 脚本单独验证较复杂，")
print("  生产环境用前端 chat-room.tsx 连接测试，此处验证 REST 部分）")
