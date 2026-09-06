# ============================================================
# Python Checkin - 后端镜像
# FastAPI + SQLAlchemy + PostgreSQL(pgvector)
# 启动时先跑 Alembic 迁移再起服务
#
# 构建思路（避免任何 C 编译器，规避国内网络下 apt/gcc 卡死）：
#   oss2 依赖 crcmod（C 扩展、无 cp312 轮子）→ 用 --no-deps 跳过，
#   由 vendor/crcmod.py（纯 Python 移植，已与官方逐字节对拍）通过
#   PYTHONPATH=/app/vendor 提供 `import crcmod`。
# ============================================================
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/vendor

WORKDIR /app

# 先装依赖（利用 Docker 层缓存，改代码不重装依赖）
COPY requirements.txt .
# 国内网络下个别大 wheel（numpy 16.7MB）从 PyPI 直下极易断流，
# 已预下载到 wheels/ 目录：numpy 显式走本地文件，其余走国内镜像（阿里云）
COPY wheels /wheels
# ① setuptools：给 --no-build-isolation 用（slim 默认不带）
# ② oss2 源码包是纯 Python，--no-deps 跳过 crcmod，--no-build-isolation 免去隔离环境联网装构建依赖
# ③ numpy 显式从 /wheels 本地 wheel 安装（pgvector 依赖它，避免大文件走网络）
# ④ 其余依赖照常装（crcmod 依赖由 vendor 提供，排除在 requirements 外）
# ⑤ 镜像源用阿里云（files.pythonhosted.org 直连在国内极不稳定，多次断流导致 hash mismatch）；
#    放宽超时 + 提高重试 + 挂载 pip 缓存层（下载过的包跨构建复用）
ARG PIP_INDEX=https://mirrors.aliyun.com/pypi/simple/
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --retries 10 --timeout 60 -i $PIP_INDEX setuptools \
    && pip install --retries 10 --timeout 60 -i $PIP_INDEX --no-build-isolation --no-deps oss2==2.19.1 \
    && pip install --retries 10 --timeout 60 /wheels/numpy-2.5.2-cp312-cp312-manylinux_2_27_x86_64.manylinux_2_28_x86_64.whl \
    && grep -v -i '^oss2' requirements.txt > /tmp/req-others.txt \
    && pip install --retries 10 --timeout 60 -i $PIP_INDEX -r /tmp/req-others.txt \
    && rm -f /tmp/req-others.txt

# 再拷贝代码（含 vendor/crcmod.py）
COPY . .

EXPOSE 8001

# 健康检查：/health 是无需鉴权的探活端点
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8001/health', timeout=3)" || exit 1

# 先跑迁移，再启动服务
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8001"]
