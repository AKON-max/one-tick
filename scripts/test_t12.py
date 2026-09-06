# 测试任务12：通知 / 文档工作室 / 知识库 / OSS / 头像
import json
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8001"


def req(method, path, body=None, token=None, raw_body=False, content_type="application/json"):
    url = BASE + path
    data = None
    headers = {}
    if body is not None:
        data = body if raw_body else json.dumps(body).encode()
        headers["Content-Type"] = content_type
    if token:
        headers["Authorization"] = f"Bearer {token}"
    r = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(r) as resp:
            payload = resp.read()
            return resp.status, json.loads(payload) if payload else None
    except urllib.error.HTTPError as e:
        payload = e.read()
        try:
            return e.code, json.loads(payload)
        except Exception:
            return e.code, payload.decode("utf-8", errors="replace")


def main():
    # 登录
    code, login = req("POST", "/api/auth/login", {"email": "http@example.com", "password": "password123"})
    assert code == 200, f"login failed: {code} {login}"
    token = login["token"]
    user_id = login["user"]["id"]
    print("[1] 登录 OK")

    # ---- 通知 ----
    # 直接通过服务造一条数据（通知由 Agent cron 生成，这里模拟）
    import sys
    sys.path.insert(0, ".")
    from app.db.session import SessionLocal
    from app.services.notification import create_notification

    with SessionLocal() as db:
        n1 = create_notification(db, user_id, "reminder", "测试提醒", "该学习了", actionUrl="/plans")
        n2 = create_notification(db, user_id, "reminder", "重复提醒", "不应出现")
        assert n1 is not None and n2 is None, "每日去重失效"
        print("[2] 通知创建 + 每日去重 OK")

    code, data = req("GET", "/api/notifications", token=token)
    assert code == 200 and data["total"] >= 1 and data["unreadCount"] >= 1, f"list failed: {data}"
    nid = data["notifications"][0]["id"]
    assert data["notifications"][0]["actionUrl"] == "/plans"
    print(f"[3] 通知列表 OK total={data['total']} unread={data['unreadCount']}")

    code, data = req("GET", "/api/notifications?unreadOnly=true&limit=5", token=token)
    assert code == 200 and all(not x["read"] for x in data["notifications"])
    print("[4] unreadOnly 过滤 OK")

    code, data = req("PATCH", f"/api/notifications/{nid}", {"read": True}, token=token)
    assert code == 200, f"mark read failed: {data}"
    print("[5] 单条标记已读 OK")

    code, data = req("POST", "/api/notifications", {"action": "markAllRead"}, token=token)
    assert code == 200 and data["markedRead"] >= 0, f"markAll failed: {data}"
    print(f"[6] 全部标记已读 OK markedRead={data['markedRead']}")

    code, data = req("POST", "/api/notifications", {"action": "xxx"}, token=token)
    assert code == 400, f"bad action should 400: {code}"
    print("[7] 非法 action 400 OK")

    code, data = req("DELETE", f"/api/notifications/{nid}", token=token)
    assert code == 200, f"delete failed: {data}"
    code, _ = req("DELETE", f"/api/notifications/{nid}", token=token)
    assert code == 404, "重复删除应 404"
    print("[8] 删除通知 + 404 OK")

    # ---- 文档工作室 ----
    code, data = req("POST", "/api/documents", {"title": "我的学习计划", "content": "# 计划\n\n1. 每天背单词"}, token=token)
    assert code == 201, f"create doc failed: {code} {data}"
    doc_id = data["document"]["id"]
    print("[9] 创建文档 OK")

    code, data = req("GET", "/api/documents", token=token)
    assert code == 200 and "content" not in data["documents"][0], "列表不应含 content"
    print("[10] 文档列表（不含 content）OK")

    code, data = req("GET", f"/api/documents/{doc_id}", token=token)
    assert code == 200 and data["document"]["content"].startswith("# 计划")
    print("[11] 文档详情 OK")

    code, data = req("PATCH", f"/api/documents/{doc_id}", {"title": "x" * 200}, token=token)
    assert code == 200 and len(data["document"]["title"]) == 120, "标题应截断 120"
    print("[12] 更新文档 + 标题截断 OK")

    long_content = "a" * 500_001
    code, data = req("POST", "/api/documents", {"title": "超大", "content": long_content}, token=token)
    assert code == 413, f"超限应 413: {code}"
    print("[13] 文档 500KB 上限 413 OK")

    code, _ = req("DELETE", f"/api/documents/{doc_id}", token=token)
    assert code == 200
    print("[14] 删除文档 OK")

    # ---- 知识库 ----
    code, data = req("GET", "/api/knowledge/documents", token=token)
    assert code == 200, f"knowledge list failed: {code} {data}"
    print("[15] 知识库文档列表 OK")

    code, data = req("POST", "/api/knowledge/documents", {"text": "太短"}, token=token)
    assert code == 400, f"过短应 400: {code}"
    print("[16] 知识库过短文本 400 OK")

    # 无 embedding key：正常文本应报 500（与原版未配置 key 行为一致）
    code, data = req("POST", "/api/knowledge/documents", {"text": "这是一段足够长的知识库测试文本。" * 10}, token=token)
    assert code == 500, f"无 key 应 500, got {code}: {data}"
    print("[17] 知识库上传（无 key → 500，符合预期）OK")

    # ---- OSS ----
    code, data = req("GET", "/api/oss/presign?ext=png", token=token)
    assert code == 503, f"未配置应 503: {code} {data}"
    code, _ = req("GET", "/api/oss/presign?ext=exe", token=token)
    assert code == 400, "非法扩展名应 400"
    code, _ = req("GET", "/api/oss/presign?ext=png&purpose=hack", token=token)
    assert code == 400, "非法用途应 400"
    print("[18] OSS 预签名：未配置 503 / 白名单 400 OK")

    # ---- 头像 ----
    code, data = req("PATCH", "/api/user/avatar", {"avatar": "3"}, token=token)
    assert code == 200 and data.get("ok"), f"预设头像失败: {data}"
    code, _ = req("PATCH", "/api/user/avatar", {"avatar": "https://evil.com/x.png"}, token=token)
    assert code == 400, "非法头像应 400"
    print("[19] 头像：预设 OK / 非法 URL 400 OK")

    print("\n=== 任务12 测试完成 ===")


if __name__ == "__main__":
    main()
