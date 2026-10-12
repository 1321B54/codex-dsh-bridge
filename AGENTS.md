# DSH bridge rules

- This repository contains the coordinator bridge, not a target project.
- The reviewed runtime is npm DSH 0.2.0-rc.2 via the local Node launcher; the Python SDK is 0.1.5rc1. Do not silently use its older bundled executable.
- Cross-process SDK session adoption is unavailable. Rework uses a fresh session with a bounded prior report and existing workspace files.
- Keep `.venv`, `.state`, credentials, session logs and task workspaces out of Git.
- Never print or commit an API token. Use Windows user-scoped DPAPI storage.
- Do not launch paid model tasks without the user's task authorization.
- Keep task execution in an explicitly approved, separate workspace. Directory selection is not a complete security boundary.
- Default to confined file writes and rejection of approval/escalation requests. Never silently fall back to full access.
- Disable optional session uploads and telemetry; ordinary API requests still send task context to the model provider.
- Model completion is not acceptance. Inspect diffs and independently run the applicable tests.
- Create local commits only after scoped review and validation. Do not push.
