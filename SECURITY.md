# Security policy

Maintainer: Jillur Rahman. Public source series: 0.6.x. No long-term support SLA or
certification is implied. Use the latest reviewed source release and maintain
FFmpeg and system dependencies separately.

Report a suspected vulnerability through this repository's **Security → Report a
vulnerability** form: https://github.com/developerjillur/ffmpeg-v2/security/advisories/new.
Do not attach credentials, private media or full personal paths to public issues.
Describe impact, affected version and a minimal reproducible case. Acknowledgment
and a fix depend on maintainer availability.

## Trust model

The toolkit runs locally with your account's permissions. Treat media parsers and
native dependencies as part of the attack surface. MCP accepts bounded typed
local-file jobs with allowlisted inputs, not arbitrary shell/raw argv. The trusted
exec CLI is intended for explicitly trusted local consumers and is not an MCP tool.
Runtime state contains filenames and logs; keep it private. The static website has
no upload endpoint, accounts or analytics.

Do not weaken path, process, timeout, disk or memory checks for an untrusted input.
Native engine/release acceptance binds actual bytes and local identity. Historical
redacted JSON reports are documentation only and cannot authorize local activation.
