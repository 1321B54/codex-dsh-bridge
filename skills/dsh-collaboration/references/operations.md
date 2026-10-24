# 执行参考

安装后入口（可从任意当前项目调用）：

Linux：

```bash
entry="$HOME/.agents/skills/dsh-collaboration/scripts/invoke-dsh.sh"
"$entry" doctor
"$entry" run --workspace project-task-unique --task-file /path/to/task-contract.md
"$entry" run --workspace project-task-unique --task-file /path/to/rework-contract.md --continue-from session-previous-id
```

Windows：

```powershell
$entry = Join-Path $HOME '.agents\skills\dsh-collaboration\scripts\invoke-dsh.ps1'
& $entry -Command doctor
& $entry -Command run -Workspace 'project-task-unique' -TaskFile 'C:\path\task-contract.md'
& $entry -Command run -Workspace 'project-task-unique' -TaskFile 'C:\path\rework-contract.md' -ContinueFrom 'session-previous-id'
```

`doctor` 不调用付费模型，只证明本地运行时初始化及凭据存在与否，不证明真实服务可用。
遇到网络失败时先执行 Linux 的 `"$entry" check-network` 或 Windows 的 `& $entry -Command check-network`：它只发送一次无凭据 HEAD 请求，不提交模型任务、不读取 Token 或项目文件。新任务会自动先做同样的检查，失败即停止派发；不以成功的 HEAD 代替付费验收。普通任务不再自动重试 5 次，协调方应查看 `network_diagnostics.error_codes`，先排除网络故障，再决定返工，不循环调用付费 `verify-live`。
DSH 请求及预检固定使用应用层直连，忽略代理环境变量和 fetch 代理分发器，不自动切换 HTTP/SOCKS 代理。不要为恢复连接擅自关闭证书验证。TUN、VPN 或路由器透明代理另受其路由规则控制，需要为 `api.deepseek.com` 配置 DIRECT 才能保证相应网络层的直连；不要把应用层直连误报为已绕过透明代理。
它返回 `doctor_mode: offline`、`paid_model_tasks: null`、`live_acceptance: not_checked`。这不是账户余额，也不否定此前付费任务成功。
只有用户明确要求实时通道检查时，执行 Linux 的 `"$entry" verify-live` 或 Windows 的 `& $entry -Command verify-live`。该命令会提交一次固定短付费任务，禁用模型工具和自动重试，不读取调用者项目；检查正确响应并由桥接创建诊断文件。
实时状态在忽略的 `.state/verify-live.json`；本次运行结果及原子用量检查点在 `.state/runs/<run_id>/result.json` / `metrics.json`。失败按鉴权、额度、限流、网络、输出上限、模型步保护或超时等类别报告。未知认证/网络状态为 null，不把失败统一解读为没有余额。
普通 run 和返工的 `usage` 只汇总本次运行；`input_tokens` 为未缓存输入，缓存计数独立，`prompt_tokens` 为所有输入，`total_tokens` 为所有输入加输出。`usage_status: partial` / `not_reported` 表示计数不完整，不能当作零费用；失败仍保留 `model_steps`、`last_finish_reason`、`session_id`。
工作区不会自动复制原项目。按显式清单选择可外发的非敏感文件，核对复制哈希；保留原 Git 基线和原有改动。不要递归复制 `.git`、`.env`、密钥、日志或依赖。
任务合同包括目标、输入、允许修改范围、禁止事项、测试和成功标准。模型上下文会发给 DeepSeek；不得夹带秘密。
返回 `run_id` 对应桥接 `.state/runs/<run_id>/result.json` 和 `progress.jsonl`。这些日志可能含代码和任务资料，禁止上传或提交。
返工创建新会话，使用同工作区实际文件及最多 12000 字符的旧报告，不恢复旧会话全历史。
凭据缺失时，让用户在桥接目录的本地交互终端执行 Linux 的 `./set-token.sh` 或 Windows 的 `./Set-Token.ps1`；不要索取聊天明文、把 Token 放入命令行、非交互输入或另开隐藏输入窗口。
认证/额度/权限/超时失败先报告，不换提供商、不关闭保护或无限重试。
