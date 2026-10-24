# Release checklist

This is a source distribution, not an npm publication. Keep `private: true`.
Do not rewrite public history. Merge reviewed contributions with their parent history.

1. Start from a clean integration clone; inspect all diffs, local rules and dependency locks.
2. Independently run `python -m unittest discover -s tests -v` with locked local dependencies. Use dummy credentials and loopback APIs only. Wait for the exact final commit's Linux CI. Record skips honestly; aarch64 and paid service acceptance are separate.
3. Keep `VERSION`, the root package version and the package-lock root version aligned. Update `CHANGELOG.md`; do not confuse the bridge version with DSH/SDK versions in `config.json`.
4. Scan the staged diff and all reachable public Git history for secrets. Inspect tracked files for local paths, personal metadata, credentials, certificates and logs. Scanners are not a guarantee.
5. Create a ZIP from the tested commit using `git -c core.autocrlf=false archive` (so Windows does not convert Linux shell entrypoints to CRLF), never by recursively zipping an installation folder. Export only public tracked source. Do not include `.git`, `.state`, `.venv`, `node_modules`, `.workspaces`, local skill mappings, certificates or private task files.
6. Inspect every uncompressed archive entry and scan its content. Privately compare the operator's known secrets against tracked and exported bytes without printing them. Verify commit author/committer privacy.
7. Compute SHA-256 over the final ZIP and provide a checksum file alongside it. Re-read both files and verify the digest before uploading.
8. Create a **draft prerelease** targeting the exact tested commit. Attach the source ZIP and checksum file. Do not mark a release as stable/latest without separate approval. Verify uploaded names, sizes and checksums against the local artifacts.
9. Publishing the draft, creating the final tag, paid service validation, and upgrading a live installation are separate actions. Never silently execute them during source packaging.

Example (PowerShell, from a clean clone after the final commit):

```powershell
$version = (Get-Content VERSION -Raw).Trim()
$ref = git rev-parse HEAD
New-Item -ItemType Directory -Force .state/releases | Out-Null
$name = "codex-dsh-bridge-$version-source.zip"
$zip = Join-Path .state/releases $name
git -c core.autocrlf=false archive --format=zip --prefix="codex-dsh-bridge-$version/" -o $zip $ref
# Inspect archive and complete the privacy checks before uploading.
$sha = (Get-FileHash $zip -Algorithm SHA256).Hash.ToLowerInvariant()
"$sha  $name" | Set-Content .state/releases/SHA256SUMS.txt -Encoding ascii
```

Installation and credential provisioning remain explicit local steps; release artifacts must never contain a working credential or machine-specific CA.
