# 测试 Agent API（临时脚本）
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

# 创建 Agent run（无 AI key，LLM 会失败但规则兜底应让 run 走完）
code, created = req("POST", "/api/agent/runs", token, {"goal": "学习 Python FastAPI", "mode": "planner"})
print(f"[2] 创建 run: status={code}, body={json.dumps(created, ensure_ascii=False)[:200]}")
assert code in (201, 400), f"create run unexpected: {code}"

if code == 201:
    run_id = created["run"]["id"]
    print(f"    run_id={run_id}, run_status={created['run']['status']}")
else:
    run_id = None

# 列表
code, runs = req("GET", "/api/agent/runs", token)
assert code == 200, f"list runs failed: {code}"
print(f"[3] 运行列表 OK: {len(runs['runs'])} 个")

# 决策列表
code, decisions = req("GET", "/api/agent/decisions", token)
assert code == 200, f"decisions failed: {code}"
print(f"[4] 决策列表 OK: {len(decisions['decisions'])} 条")

# 决策统计
code, stats = req("GET", "/api/agent/decisions/stats", token)
assert code == 200, f"decision stats failed: {code}"
print(f"[5] 决策统计 OK: {json.dumps(stats, ensure_ascii=False)[:150]}")

# cron 巡检（对所有用户跑，无 key 时靠规则兜底）
code, cron = req("POST", "/api/agent/cron/daily", token)
print(f"[6] cron 巡检: status={code}, body={json.dumps(cron, ensure_ascii=False)[:200]}")

print("\n=== Agent API 测试完成 ===")
