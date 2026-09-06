# 测试会话 API（临时脚本）
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

# 创建会话
code, conv = req("POST", "/api/conversations", token, {"title": "测试对话"})
assert code == 201, f"create conv failed: {code}"
conv_id = conv["id"]
print(f"[2] 创建会话 OK: {conv_id}")

# 会话列表
code, convs = req("GET", "/api/conversations", token)
assert code == 200 and len(convs) >= 1, "list convs failed"
print(f"[3] 会话列表 OK: {len(convs)} 个")

# 会话详情
code, detail = req("GET", f"/api/conversations/{conv_id}", token)
assert code == 200, "get conv failed"
print(f"[4] 会话详情 OK: title={detail['title']}")

# 改标题
code, _ = req("PATCH", f"/api/conversations/{conv_id}/title", token, {"title": "改后的标题"})
assert code == 200, "patch title failed"
code, detail = req("GET", f"/api/conversations/{conv_id}", token)
assert detail["title"] == "改后的标题"
print("[5] 改标题 OK")

# 消息列表（空）
code, msgs = req("GET", f"/api/conversations/{conv_id}/messages", token)
assert code == 200 and len(msgs) == 0, "messages should be empty"
print("[6] 消息列表 OK (空)")

print("\n=== 会话 API 测试通过 ===")
