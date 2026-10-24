# Changelog

## 1.0.0-rc.1 — 2026-10-24

首个候选发行版（实验性社区桥接，非 OpenAI / DeepSeek 官方产品）。

### 功能

- 合入 Windows / Linux 入口、便携技能安装、当前聊天手动开关，以及运行用量和失败分类。
- 合入 PR #2：无凭据 HEAD 网络预检、`check-network` 命令、白名单网络错误码、关闭自动模型重试。
- 默认输出上限从 8192 提高至 393216（384K）；600 秒超时、12 模型步和任务文件大小限制保持不变。
- 固定 DSH npm 运行时 `0.2.1-rc.2` 与 Python SDK `0.2.1rc2`，通过显式 Node 启动器运行。

### 合并修复与安全边界

- 解决 PR #2 与主分支冲突，同时保留任务级 Agent home 隔离、可选的进程级 CA 哈希校验和新增工具禁用项。
- 保留 `workspace-write` / `never`，不自动升级权限；Windows 使用 DPAPI，Linux 使用权限受限但未加密的凭据文件。
- 新增直连启动器与临时 CA 的组合回归测试：已批准 CA 可连接，证书被改动后拒绝启动。
- 原有公开提交及贡献者提交保留，不压缩或重写历史。

### 升级注意

- **固定直连**：不再使用 HTTP/SOCKS 显式代理、代理环境变量或 `NODE_OPTIONS` 注入的代理。必须经显式代理才能访问服务的环境可能无法使用此版；不更改系统代理或透明路由。
- **费用**：更高输出上限可能增加费用；上限不是实际用量或金额预算，也不是无限输出。当前官方规格见 [模型与价格](https://api-docs.deepseek.com/quick_start/pricing/)。
- 网络预检仅证明当时的 TLS/HTTP 可达；`doctor` 不验证真实凭据，`verify-live` 会发送小额付费请求，需另行授权。
- 安全边界并非完整多租户隔离。特别是模型 shell 可能访问运行时凭据；请先阅读 [安全策略](SECURITY.md)，对不可信任务使用专用低额度密钥及隔离环境。
- 源码包不含凭据、证书、日志、运行时或依赖，需要按 README 安装锁定依赖。升级应备份并保留本机 `.state`、自定义配置和技能映射，禁止上传这些内容。

### 验证范围

离线测试使用虚构凭据、临时工作区和回环假 API；不等同于真实付费服务验收。
Windows 本机和 GitHub Actions Linux x86_64 分别验证；Linux aarch64 提供锁文件，未做本次原生设备验收。
此版仅准备候选发行包，不自动更新任何已安装的桥接或用户技能。

## 2026-10-24

- Update the default-channel Node runtime to `0.2.1-rc.2` and the Python SDK/runtime
  wheel to `0.2.1rc2`; refresh Windows and Linux hash locks.
- Pin compatible dependency security fixes for MCP client, fflate, undici and Zod.
- Add opt-in, hash-pinned, process-local CA trust without disabling TLS validation.
- Keep shared agent instructions inside each task home and disable newly exposed
  working-directory/dependency-download tools instead of expanding worker scope.
- Fix UTF-8 output for PowerShell skill entrypoints in non-ASCII project paths.
- Preserve Linux support, explicit live diagnostics, usage accounting and manual
  per-chat opt-in. Keep fresh-session rework; do not automatically adopt the new
  SDK resume API or enable parallel dispatch.
