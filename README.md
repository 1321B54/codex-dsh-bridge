# Codex DSH Bridge (Windows / Linux)

Codex 负责规划、审查和验收，DeepSeek Harness 执行明确、有限的子任务。
这是独立的社区桥接，不是 OpenAI 或 DeepSeek 官方集成。不承诺固定省费比例。

## Linux 安装

需要 Python 3.14、Node.js 24、npm 和 Bash；支持 glibc Linux x86_64/aarch64，当前实测为 x86_64。先从官方渠道安装这些工具，在仓库目录运行：

```bash
./setup.sh
./install-skill.sh   # 可选：用户级技能；拒绝覆盖同名技能
./set-token.sh       # 在自己的交互终端隐藏输入，不发到聊天
./dsh-task.sh doctor
```

可用 `DSH_PYTHON=/path/to/python3.14 ./setup.sh --node /path/to/node --npm /path/to/npm` 选择已有工具。安装只创建本地 `.venv`、`node_modules`、`.state`，不安装全局软件或修改系统配置；Python 使用 Linux wheel 哈希锁，npm 生命周期脚本关闭。机器路径只写入忽略的 `.state/runtime-launch.json`。

Linux Token 保存在 `.state/token.credentials`：目录权限 `0700`，文件权限 `0600`，**文件内容未加密**，读取时拒绝符号链接、硬链接和不安全权限；同用户程序及 root 仍可读取。Windows 继续使用 DPAPI，不会转换已有凭据。Linux 运行时使用 Bash 和上游的 bwrap/Landlock 沙箱；沙箱不可用时拒绝 shell 执行，不退回全权限。`doctor` 只检查 SDK 初始化，不能代替实际 shell 沙箱测试。

用户级技能位置为 `~/.agents/skills/dsh-collaboration`（见 [Codex 技能文档](https://learn.chatgpt.com/docs/build-skills)）；可用 `./install-skill.sh --skill-root /absolute/path` 指定目录。安装映射只在本机生成。自然语言启用方式与 Windows 相同。安装不派发任务；凭据和真实服务尚需用户自行配置与验证。

```bash
./dsh-task.sh run --workspace task01 --task-file /path/to/task.md
./dsh-task.sh run --workspace task01 --task-file /path/to/rework.md --continue-from session-previous-id
# 可从其他项目调用安装的技能入口：
~/.agents/skills/dsh-collaboration/scripts/invoke-dsh.sh doctor
```

## Windows 安装

需要 Windows、Python 3.14、Node.js 24、PowerShell 7 和 npm（先从各自官方渠道安装）。
审查源码后在仓库目录运行：

```powershell
./Setup.ps1
./Install-Skill.ps1  # 可选：当前用户级技能；已有同名技能时拒绝覆盖
./Set-Token.ps1     # 在自己的交互终端隐藏输入，不发到聊天
./dsh-task.ps1 -Command doctor
```

Setup 安装本地 `.venv` 和 `node_modules`，不修改系统 Python 或安装全局软件；使用锁定依赖，npm 生命周期脚本关闭。
Node/PowerShell 的机器路径仅写入忽略的 `.state/runtime-launch.json`，安装技能的路径映射也只在本机生成。
用户级技能目录是 `$HOME/.agents/skills/dsh-collaboration`；新技能未被发现时重启 Codex。
自然语言“用 DSH 协作模式”“启用 DSH”或 `$dsh-collaboration` 请求协作。只有启用、没有具体任务时，不调用付费模型。

## 派发与返工

协调方先检查原项目 Git 状态，按明确清单把非敏感、允许外发的输入放入本仓库忽略的 `.workspaces/task01`。
不要复制整个项目、`.git`、`.env`、密钥、日志或依赖。示例任务合同见 `task-template.md`。

```powershell
./dsh-task.ps1 -Command run -Workspace task01 -TaskFile C:\path\task.md
./dsh-task.ps1 -Command run -Workspace task01 -TaskFile C:\path\rework.md -ContinueFrom session-previous-id
```

返回 `model_completed=true` 只说明执行结束；`accepted_by_coordinator` 永远为 false，主助手必须独立审查差异和测试。
SDK 不支持跨进程采用已有会话；返工新建会话，带上最多 12000 字符旧报告和当前工作区文件。
一次只派发一个任务。失败、取消、超时均可能留下部分编辑；停止不回滚。残留锁必须先确认无活动任务，再人工处理。

## 固定版本与限制

- 官方 Node DSH `@deepseek-ai/dsh@0.2.0-rc.2`、Python SDK `0.1.5rc1`；不使用 SDK 捆绑旧 SEA 运行时。
- `deepseek-flash`，官方 Messages 根地址 `https://api.deepseek.com/anthropic`；修改端点被拒绝。
- `workspace-write` + `never`（拒绝审批升级，不是自动批准）。不自动 fallback 为全权限。
- 600 秒超时，8192 单响应 token，12 模型步软保护；不是精准账单预算，通知时序、输入、重试、缓存或压缩可能影响费用。
- Windows Job 在超时/取消/父进程退出时停止工作进程及其后代。Linux 使用独立守护进程、生命周期管道和子进程收养；包括 shell 新建会话的后代，在正常结束、超时、取消或协调进程被终止时清理。守护进程自身遭 SIGKILL/系统崩溃不在此保证内。
- 禁用额外会话日志上传、遥测、插件清单上传、网页工具及子 Agent/循环目标工具。

## 隐私和安全

详见 [SECURITY.md](SECURITY.md)。DPAPI 只保护当前 Windows 用户之外的常规解密；不抵御同用户恶意程序或管理员。
Windows 沙箱是部分隔离，不保证读取、网络和进程隔离，也不保证所有 NTFS 硬链接边界。模型 shell 可读取它自己的环境，包括运行时 API 凭据。
不要处理敌意项目或机器上有敏感信息的任务；强隔离需专用非特权账户/虚拟机/网络策略。
“关闭额外上传”不是离线：真正执行时，任务、读取的文件内容和工具结果仍发送给 DeepSeek。
`.state` 包含凭据（Windows 密文、Linux 明文）、上下文和日志；`.workspaces` 是任务文件；均禁止发布。Git ignore 不是防泄漏保证。

## 离线测试

Linux：

```bash
./.venv/bin/python -m unittest discover -s tests -v
```

Windows：

```powershell
./.venv/Scripts/python.exe -m unittest discover -s tests -v
```

测试用本地模拟 Messages 服务配合真实锁定运行时，不用真实 Token、无付费模型请求。平台专属测试在其他平台显式跳过。Linux 另外覆盖私有凭据权限、符号/硬链接拒绝、Bash 写入及越界拒绝、独立会话子进程在超时/协调进程 SIGKILL 后清理。
覆盖 DPAPI dummy roundtrip、路径/配置拒绝、环境清理、进程树超时、事件计数、文件/命令写入及越界拒绝、升级拒绝和新会话返工。
这不等于真实 API 账户或所有 Windows 主机/沙箱边界的验收。

官方资料：[Python SDK](https://github.com/deepseek-ai/deepseek-harness/blob/master/docs/user/guide/python-sdk.md)、[Protocol](https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/sdk/protocol/README.md)、[Safety](https://github.com/deepseek-ai/deepseek-harness/blob/master/SAFETY.md)。
上游文档可能快于锁定版本，以测试证据为准。
