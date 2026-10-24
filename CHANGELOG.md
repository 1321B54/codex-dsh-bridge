# Changelog

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
