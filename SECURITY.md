# Security policy

This bridge is an experimental Windows/Linux local coordinator, not a hardened multi-tenant execution service.

## Trust model

- The operator, installation scripts, runtime packages, config and current OS account are trusted.
- Model output, task code and copied repository content are untrusted. Prompts are not access-control enforcement.
- Linux stores the credential **without encryption** in a current-user-owned 0600 file beneath a 0700 state directory. Reads reject symlinks, hardlinks, foreign ownership and unsafe modes. Same-user programs and root can read it. A Linux installation does not import Windows credentials.
- DPAPI is current-user scoped. Same-user processes, administrators and a compromised runtime can recover/use the API credential.
- The execution runtime must receive the API key. Child commands inherit it: a model-directed shell can disclose it. Do not run adversarial tasks with a valuable account. Use a dedicated limited account/key and disposable VM for stronger separation.
- Windows workspace-write confinement is partial: read, network, process visibility and all filesystem alias/hardlink cases are NOT guaranteed. Disabled extra uploads do not prevent normal model requests or shell network traffic.
- Linux shell confinement uses upstream bwrap or Landlock and fails closed if neither works. Enforcement varies with kernel/backend; Landlock does not provide full read, network or process isolation. Linux cleanup uses a separate guardian, a coordinator lifetime pipe and child subreaping, including detached shell sessions. It is lifecycle management, not a hostile-process boundary: killing the guardian with SIGKILL, a kernel failure or an unkillable process can defeat cleanup.
- API-key pattern checks and output redaction are defense-in-depth, not general DLP. Task files and tools may contain other secrets; inspect them before dispatch.
- Timeout/model-step/output caps limit some work, not a currency budget. Cancellation is not rollback.

## Publication

Never commit `.state`, `.workspaces`, `.venv`, `node_modules`, `.env*`, private keys, logs, installed skill path mappings, local runtime paths or credential files. Inspect staged data AND every reachable Git revision and archive; ignored files can still be explicitly added.
Use a clean source-only export and non-personal author metadata when sharing someone else's local installation. Never publish its original `.git` history.

## Reporting

Report suspected vulnerabilities privately through GitHub private vulnerability reporting if enabled. Otherwise open an issue without secrets/exploit credentials and ask for a private contact channel. Never attach API keys, personal task files or logs. No response-time SLA is promised.
