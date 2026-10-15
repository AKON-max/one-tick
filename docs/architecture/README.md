# Architecture Artifacts

该目录保存 One-Tick 的运行时架构说明和可浏览产物。

| 文件 | 说明 |
|---|---|
| `runtime-topology.md` | 架构说明、分层职责和关键取舍 |
| `overview.svg` | 轻量矢量总览，适合文档嵌入 |
| `overview.png` | 完整静态预览图 |
| `overview.html` | 可独立打开的交互式架构图 |
| `overview.json` | Archify 架构源文件 |

维护规则：

1. 架构发生变化时先修改 `overview.json`。
2. 重新生成 `overview.html` 和 `overview.png`。
3. 同步更新 `runtime-topology.md`。
4. 不要把凭据、真实服务器地址或本地路径写入图中。