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
工作区不会自动复制原项目。按显式清单选择可外发的非敏感文件，核对复制哈希；保留原 Git 基线和原有改动。不要递归复制 `.git`、`.env`、密钥、日志或依赖。
任务合同包括目标、输入、允许修改范围、禁止事项、测试和成功标准。模型上下文会发给 DeepSeek；不得夹带秘密。
返回 `run_id` 对应桥接 `.state/runs/<run_id>/result.json` 和 `progress.jsonl`。这些日志可能含代码和任务资料，禁止上传或提交。
返工创建新会话，使用同工作区实际文件及最多 12000 字符的旧报告，不恢复旧会话全历史。
凭据缺失时，让用户在桥接目录的本地交互终端执行 Linux 的 `./set-token.sh` 或 Windows 的 `./Set-Token.ps1`；不要索取聊天明文、把 Token 放入命令行、非交互输入或另开隐藏输入窗口。
认证/额度/权限/超时失败先报告，不换提供商、不关闭保护或无限重试。
