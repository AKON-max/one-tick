# 补测 multipart 分支：文档导入 .md 文件 + 知识库文件上传（含非法格式 400）
import io
import json
import urllib.error
import urllib.request
import uuid

BASE = "http://127.0.0.1:8001"


def multipart(path: str, fields: dict, files: dict, token: str):
    boundary = uuid.uuid4().hex
    parts = []
    for k, v in fields.items():
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n')
    for name, (filename, data, ctype) in files.items():
        parts.append(
            f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"; filename="{filename}"\r\n'
            f"Content-Type: {ctype}\r\n\r\n"
        )
        parts.append(data.decode("utf-8") if isinstance(data, bytes) else data)
        parts.append("\r\n")
    parts.append(f"--{boundary}--\r\n")
    body = "".join(p if isinstance(p, str) else p for p in parts)
    r = urllib.request.Request(
        BASE + path,
        data=body.encode("utf-8"),
        method="POST",
        headers={
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "Authorization": f"Bearer {token}",
        },
    )
    try:
        with urllib.request.urlopen(r) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", errors="replace")


def main():
    body = json.dumps({"email": "http@example.com", "password": "password123"}).encode()
    r = urllib.request.Request(BASE + "/api/auth/login", data=body, method="POST")
    r.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(r) as resp:
        token = json.loads(resp.read())["token"]

    # 1. 文档导入 .md 文件（无 title 表单字段 → 文件名去扩展名）
    md = "# 导入的计划\n\n## 第一阶段\n\n背单词"
    code, data = multipart(
        "/api/documents", {}, {"file": ("plan.md", md.encode(), "text/markdown")}, token
    )
    assert code == 201, f"doc import failed: {code} {data}"
    assert data["document"]["title"] == "plan" and data["document"]["content"].startswith("# 导入的计划")
    print("[1] 文档导入 .md 文件 OK title=plan")

    # 2. 文档导入带 title 表单字段
    code, data = multipart(
        "/api/documents", {"title": "指定标题"}, {"file": ("x.txt", b"hello txt", "text/plain")}, token
    )
    assert code == 201 and data["document"]["title"] == "指定标题"
    print("[2] 文档导入 + 表单标题 OK")

    # 3. 知识库上传 .md 文件（无 key → 500，与 JSON 路径一致）
    code, _ = multipart("/api/knowledge/documents", {}, {"file": ("kb.md", md.encode(), "text/markdown")}, token)
    assert code == 500, f"expected 500, got {code}"
    print("[3] 知识库 .md 文件上传（无 key → 500）OK")

    # 4. 知识库上传非法格式 → 400
    code, _ = multipart("/api/knowledge/documents", {}, {"file": ("bad.exe", b"MZ...", "application/octet-stream")}, token)
    assert code == 400, f"expected 400, got {code}"
    print("[4] 知识库非法格式 400 OK")

    print("\n=== multipart 补测完成 ===")


if __name__ == "__main__":
    main()
