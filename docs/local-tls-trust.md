# Optional process-local TLS trust

The Node launcher accepts one explicitly approved additional public CA from local
state. This can support an administrator-approved HTTPS inspection certificate
without disabling TLS validation or changing the operating system's trust store.

Add both fields to the local, Git-ignored `.state/runtime-launch.json`:

```json
{
  "extra_ca_file": "tls/approved-root.pem",
  "extra_ca_sha256": "<SHA-256 of the exact approved PEM bytes>"
}
```

Keep the existing Node and shell paths. The certificate path is relative to
`.state`. Verify the CA's identity, fingerprint, validity, and local trust before
exporting its **public certificate only**. Never export a private key or accept an
unknown certificate merely to suppress an error.

The launcher rejects path escapes, symlinks/junctions, changed hashes, invalid
PEM, private-key material, and conflicting inherited Node CA configuration.
Only launched DSH processes receive `NODE_EXTRA_CA_CERTS`; hostname and chain
verification remain enabled. With no opt-in, existing trust remains unchanged.
Do not use `NODE_TLS_REJECT_UNAUTHORIZED=0`.

Remove both optional fields to disable the additional CA for new workers. Back up
local configuration before changes; never publish certificate files, machine
paths, credentials, or runtime logs. A successful TLS handshake does not prove a
paid model task or a coding change has passed acceptance.
