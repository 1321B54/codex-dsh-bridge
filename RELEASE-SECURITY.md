# Release security checks

Checked on 2026-10-12, Windows. This is measured release evidence, not a guarantee of vulnerability-free code or a hardened adversarial execution sandbox.

## Publication privacy gate

- Independent offline source review identified machine-specific directory metadata in the private installation's source. The public copy replaces it with portable locations and generates installed path mappings locally.
- Public Git history starts fresh with nonpersonal contributor metadata. Original Git history, author identity, credentials, machine state, dependencies and task logs are not published.
- Explicit source-file allowlist; `.state`, `.workspaces`, `.venv`, `node_modules`, installed skill mappings and private files are excluded independently of Git ignore rules.
- Private offline exact-match checking uses the operator's configured provider credential and Git credential only in memory, including common encoded forms; none is printed, written into source or sent to scanners.
- Public source, staged contents, every reachable release commit and the Git archive are checked for credentials, personal paths and private metadata. Gitleaks 8.30.1 provides an additional redacted source/history/archive scan.
- The source-only audit's detailed artifacts remain local: they may contain machine paths and are deliberately NOT included here.

## Dependency checks and hardening

- npm production audit found two underlying advisory families in the original dependency tree (12 affected/propagated package entries, not 12 independent bugs).
- The public copy overrides `@modelcontextprotocol/client` to `2.2.0` for [GHSA-6qxp-vccf-f47h](https://github.com/advisories/GHSA-6qxp-vccf-f47h), and `fflate` to `0.8.3` for [GHSA-px8p-9vwx-vf98](https://github.com/advisories/GHSA-px8p-9vwx-vf98).
- Repeat npm production audit: zero known vulnerabilities in the checked lock. This does not prove vulnerability absence or all optional MCP/office paths' compatibility.
- pip-audit 2.10.1 checked all seven pinned runtime packages: zero known vulnerabilities, no skipped packages. The complete lock uses SHA-256 wheel hashes for Windows x64/Python 3.14; Setup enforces `--require-hashes` with binary-only, isolated pip and disables npm lifecycle scripts.
- Bandit 1.9.4 checked production Python. No high/medium findings; low subprocess warnings are reviewed: fixed argument arrays, no shell interpolation, trusted pinned runtime and Windows system-directory executable lookup. Low heuristic findings are not hidden or represented as zero findings.
- Runtime launcher rejects relative or missing executable paths. Setup validates both supplied Python and an existing virtualenv. Skill installation stages an explicit file list and uses a no-replacement directory move.

## Runtime and behavioral checks

The offline unittest suite passes 34 checks using a real pinned DSH runtime and a loopback fake Messages provider, without a real Token or a paid model call. Coverage includes:

- DPAPI dummy round trip; credential/environment scrubbing; noninteractive token-entry rejection.
- Workspace/name/root checks, including real Windows junction-root and junction-workspace escape rejection.
- Nonprefixed active-credential rejection before task dispatch; same policy applied to rework text.
- Windows Job descendant termination; timeout and malformed-result handling; actual runtime step-event counting.
- Workspace file and shell writes, outside-write rejection, rejected full-access escalation and fresh-session rework.
- Cross-project/source-skill invocation, missing-install failure, generated mapping/installed entry, and preservation of an existing skill.

## Remaining limits

Read [SECURITY.md](SECURITY.md) before use. The runtime and model-directed child shell can access runtime API credentials, and Windows confinement does not guarantee read/network/process isolation. Source selection and limited-key/VM boundaries remain operator responsibilities. Only selected runtime paths were tested; this is not a full audit of every upstream dependency, real-provider service acceptance, an exact money budget, or a benchmark proving a savings ratio.


## Linux adaptation evidence (2026-10-13)

Validated on Linux x86_64 with CPython 3.14 and Node.js 24, using the same pinned SDK/runtime. The Linux lock includes published PyPI wheel hashes for glibc x86_64/aarch64; aarch64 has not been executed here. Original Windows evidence above is historical, not a new Windows validation.

- Linux local setup, SDK doctor and source/installed skill entrypoints pass without a real API credential or paid request.
- Real runtime with a loopback fake Messages service passes file/Bash writes, outside-write denial, approval rejection, event accounting and fresh-session rework.
- Linux-specific tests verify private state/token permissions, dummy credential roundtrip, unsafe-mode/symlink/hardlink rejection and environment scrubbing.
- Actual detached subprocesses are stopped on normal completion, timeout, cancellation (return code 130) and coordinator SIGKILL; a guardian adopts orphaned descendants because DSH shells can start independent sessions.
- Existing skill preservation is tested. Installation uses Linux `renameat2(RENAME_NOREPLACE)` so concurrent destinations, including empty directories, are not replaced.
- Linux credentials are not encrypted. No real-provider account/credit check, aarch64 acceptance, new Windows run or new dependency security audit is claimed.
