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

用户级技能位置为 `~/.agents/skills/dsh-collaboration`（见 [Codex 技能文档](https://learn.chatgpt.com/docs/build-skills)）；可用 `./install-skill.sh --skill-root /absolute/path` 指定目录。安装映射只在本机生成。手动开启规则与 Windows 相同，见下文。安装本身不派发任务；凭据和真实服务尚需用户自行配置与验证。

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

## 手动开启 DSH 辅助

每个新聊天默认关闭；普通开发需求不会自动启用 DSH。技能描述只匹配明确的 DSH 开关或使用请求；`allow_implicit_invocation: true` 用于识别这些口令，不代表自动授权付费执行。

直接在聊天中输入以下命令，不需要运行终端：

| 聊天命令 | 作用 |
| --- | --- |
| `开启 DSH 辅助` / `开启 DSH` | 开启当前聊天的辅助模式；仅开启不发送付费请求 |
| `关闭 DSH 辅助` / `关闭 DSH` | 停止后续派发，后续任务由 Codex 直接处理 |
| `这次不用 DSH` | 仅跳过当前任务，不改变之后的模式 |
| `$dsh-collaboration 开启` / `$dsh-collaboration 关闭` | 显式指定技能并切换模式 |

开启后由 Codex 拆分任务、调用 DSH、审查和整合结果。开关是聊天上下文中的模式，不是桥接 CLI 子命令或跨聊天共享状态；不会改 Token、模型或安全配置。关闭不会仅凭聊天指令自动取消已经运行的任务。新规则未被加载时新开聊天或重启 Codex。

## 离线诊断与实时检查

`doctor` **不产生付费请求**，只做本地 SDK 初始化和凭据文件存在检查。它返回 `doctor_mode: "offline"`、`paid_model_tasks: null`、`live_acceptance: "not_checked"`，认证及网络字段为 `null`。这些值表示本次未检查远端，不否定此前成功的调用；`model_requests_submitted: 0` 仅表示本次 doctor 没有提交模型请求。**paid_model_tasks 不是账户余额**，本工具不查询余额、账单或历史付费任务数。

需要检查真实凭据和付费通道时，显式运行：

```bash
./dsh-task.sh verify-live
~/.agents/skills/dsh-collaboration/scripts/invoke-dsh.sh verify-live
```

Windows 对应 `./dsh-task.ps1 -Command verify-live` 或技能入口的 `-Command verify-live`。

`verify-live` **会产生一次很小的付费请求**：提交一个固定短任务，要求返回 `DSH_LIVE_VERIFY_OK`。它使用新的隔离诊断工作区和运行时 home，禁用模型工具、项目指令/技能发现及自动模型重试，不读取或复制调用者项目文件，不改变调用者项目。收到正确响应后由桥接在诊断工作区创建并校验固定内容的 `verified.txt`；这证明 API/SDK 通道及本地诊断文件校验，不单独证明模型 shell 沙箱。保留原 provider、模型、8192 输出上限、12 步软保护和沙箱策略。输出上限不是实际用量或金额上限；实际费用以服务商及返回用量为准。

成功返回 `credential_valid: true`、`api_reachable: true`、`live_acceptance: "passed"`，以及 `model`、`finish_reason`、`model_steps` 和本次汇总 `usage`。最新检查存入忽略的 `.state/verify-live.json`，对应运行存入 `.state/runs/<run_id>/result.json`。离线 doctor 不会把历史实时检查当作当前认证状态，也不会自动调用 verify-live。

失败的 `failure_category` 区分 `authentication`（鉴权失败）、`quota`（服务商明确报告余额/额度不足）、`rate_limit`（请求限流，不能据此判断余额）、`network`、`provider`（服务端故障）、`max_tokens`、`model_step_guard`、`timeout`、`interrupted` 和 `runtime`。响应内容或诊断文件校验失败为 `verification_failed`；缺少本机凭据为 `credential_missing`。无法证明的 `credential_valid` / `api_reachable` 返回 `null`，不是一律返回“没有钱”。

## 运行用量与失败证据

普通 `run` 和返工的 `result.json` 新增 `usage`、`usage_status`、`reported_model_requests`、`model_attempts`、`last_finish_reason` 和结构化失败类别。`session_id`、旧结果字段及 `run` / `--continue-from` 参数保持兼容。用量只统计本次运行，不叠加返工前的费用。

`usage` 字段使用 snake_case：`input_tokens` 是锁定 SDK 报告的**未缓存输入**；`cache_read_tokens`、`cache_write_tokens` 为分开的缓存输入，`cache_tokens` 是两者之和；`prompt_tokens` 为未缓存输入加缓存输入；`output_tokens` 为输出；`total_tokens` 包括所有输入及输出。`reasoning_tokens` 仅在运行时报告时提供，不能再次加进总量。

按每个已落盘的 `assistant/message` / `assistant/attempt` 汇总一次；重复事件去重，失败流内的累计快照只取最后一个，避免重复计费。每次事件都原子保存纯数字统计至 `.state/runs/<run_id>/metrics.json`，因此 max-tokens、13th-step guard、超时及中断后仍能保留已收到的 `model_steps`、`usage`、`last_finish_reason` 和 `session_id`。`last_finish_reason` 是最后收到的运行时终止原因；没有收到时为 `null`，实际桥接停止原因另见 `failure_category`。

运行时尚未报告的用量为 `null`，`usage_status: "not_reported"`；缺少某次调用计数或被终止的未完成步骤为 `"partial"`；已收到的完整响应计数为 `"reported"`。部分统计仅代表已知用量，**不代表尚未收到计数的请求免费**，也不代替服务商账单。历史 `result.json` 不自动重写；新统计从本次修复后的运行开始。

## 派发与返工

协调方先检查原项目 Git 状态，按明确清单把非敏感、允许外发的输入放入本仓库忽略的 `.workspaces/task01`。
不要复制整个项目、`.git`、`.env`、密钥、日志或依赖。示例任务合同见 `task-template.md`。

```powershell
./dsh-task.ps1 -Command run -Workspace task01 -TaskFile C:\path\task.md
./dsh-task.ps1 -Command run -Workspace task01 -TaskFile C:\path\rework.md -ContinueFrom session-previous-id
```

返回 `model_completed=true` 只说明执行结束；`accepted_by_coordinator` 永远为 false，主助手必须独立审查差异和测试。
桥接仍按原策略返工：新建会话，带上最多 12000 字符旧报告和当前工作区文件。新版 SDK 支持持久化恢复，但本桥接未启用。
一次只派发一个任务。失败、取消、超时均可能留下部分编辑；停止不回滚。残留锁必须先确认无活动任务，再人工处理。

## 固定版本与限制

HTTPS 检查软件导致的证书链问题，可按[仅对 DSH 补充本机 CA 信任](docs/local-tls-trust.md)配置；不关闭 TLS 校验、不上传证书文件。

- 官方 Node DSH `@deepseek-ai/dsh@0.2.1-rc.2`、Python SDK `0.2.1rc2`；继续使用已验证的 Node 启动入口，不自动切换到 SDK 捆绑运行时。
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
