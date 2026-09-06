# 端到端测试核心业务 API（临时脚本）
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


# 1. 登录
code, login = req("POST", "/api/auth/login", body={"email": "http@example.com", "password": "password123"})
assert code == 200, f"login failed: {code}"
token = login["token"]
user_id = login["user"]["id"]
print(f"[1] 登录 OK, user={user_id}")

# 2. 打卡
code, checkin = req("POST", "/api/checkins/daily", token, {"mood": "开心", "scene": "rain"})
assert code == 200, f"checkin failed: {code}"
print(f"[2] 打卡 OK: {checkin['checkin']['content']}")

# 重复打卡应 409
code, _ = req("POST", "/api/checkins/daily", token, {"mood": "开心"})
assert code == 409, f"duplicate checkin should 409, got {code}"
print("[2] 重复打卡拦截 OK (409)")

# 3. 计划列表（应有注册时克隆的引导计划）
code, plans = req("GET", "/api/plans", token)
assert code == 200 and len(plans) >= 1, f"plans failed: {code}"
plan = plans[0]
print(f"[3] 计划列表 OK: {len(plans)} 个, 第一个: {plan['name']}")

# 4. 计划任务（引导计划应有 6 个任务）
code, tasks_data = req("GET", f"/api/plans/{plan['id']}/tasks", token)
assert code == 200 and len(tasks_data["tasks"]) >= 1, f"tasks failed: {code}"
print(f"[4] 任务列表 OK: {len(tasks_data['tasks'])} 个, stale={tasks_data['stale']}")

# 5. 更新任务状态
task = tasks_data["tasks"][0]
code, updated_task = req("PATCH", f"/api/plans/{plan['id']}/tasks", token, {"taskId": task["id"], "status": "done"})
assert code == 200 and updated_task["status"] == "done", f"task update failed: {code}"
print(f"[5] 任务状态更新 OK: {task['title'][:20]}... -> done")

# 6. 新建计划（带默认任务）
code, created = req("POST", "/api/plans", token, {"name": "测试计划", "goal": "学会 FastAPI"})
assert code == 201, f"create plan failed: {code}"
new_plan_id = created["plan"]["id"]
code, new_tasks = req("GET", f"/api/plans/{new_plan_id}/tasks", token)
assert code == 200 and len(new_tasks["tasks"]) == 5, f"new plan tasks failed: {len(new_tasks['tasks'])}"
print(f"[6] 新建计划 OK: 自动生成 {len(new_tasks['tasks'])} 个默认任务")

# 7. 待办
code, todo = req("POST", "/api/todos", token, {"title": "完成认证模块"})
assert code == 201, f"create todo failed: {code}"
code, _ = req("PATCH", f"/api/todos/{todo['id']}", token, {"completed": True})
assert code == 200, "update todo failed"
code, todos = req("GET", "/api/todos", token)
assert code == 200 and len(todos) >= 1, "list todos failed"
print(f"[7] 待办 OK: 创建+完成+列表 ({len(todos)} 条)")

# 8. 专注会话
code, focus = req("POST", "/api/focus/sessions", token, {"durationMinutes": 25, "sessionId": "focus-test-001"})
assert code == 200 and focus["ok"], f"focus failed: {code}"
code, dup = req("POST", "/api/focus/sessions", token, {"durationMinutes": 25, "sessionId": "focus-test-001"})
assert dup.get("duplicate") is True, "focus duplicate should be detected"
print("[8] 专注会话 OK (含幂等去重)")

# 9. 统计
code, stats = req("GET", "/api/statistics/overview", token)
assert code == 200, f"stats failed: {code}"
print(f"[9] 统计 OK: totalCheckins={stats['totalCheckins']}, streak={stats['streak']}, activePlans={len(stats['activePlans'])}")

code, focus_stats = req("GET", "/api/statistics/focus", token)
assert code == 200 and len(focus_stats["days"]) == 7, "focus stats failed"
print(f"[10] 专注统计 OK: 7 天数据, 今天 {focus_stats['days'][-1]['minutes']} 分钟")

print("\n=== 全部核心业务 API 测试通过 ===")
