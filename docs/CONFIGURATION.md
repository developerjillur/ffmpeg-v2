# Workspace and resource configuration

Set these before launching the CLI, Python process or MCP server. The configuration
is captured when modules load. Use absolute paths in long-running clients.

| Variable | Default | Meaning |
|---|---|---|
| FFV2_PROJECT_ROOT | Current working directory | Allowed media project and default .runtime parent. |
| FFV2_WORK_ROOT | PROJECT/.ffv2-work | Scratch/native build workspace. Large artifacts use WORK/Work. |
| FFV2_STATE_DIR | PROJECT/.runtime | Private SQLite queue, plans, receipts and logs; must remain inside allowed output roots. |
| FFV2_HOST_LOCK | ~/Library/Caches/ffmpeg-v2/host.lock | Shared lock across this user's workspaces. Keep it shared to prevent competing heavy workers. |
| FFV2_REQUIRED_MOUNTS | Empty | Colon-separated explicit mount roots; relevant paths fail closed when a mount is absent. |
| FFV2_FFMPEG / FFV2_FFPROBE | ffmpeg / ffprobe on PATH | Explicit backend executables, unless a verified installed release forbids overrides. |
| FFV2_BOOT_USED_LIMIT_BYTES | Unset | Optional owner-defined ceiling on boot disk used bytes. Positive decimal byte count required. |
| FFV2_LAB_ROOT | WORK/Work | Optional root for archived research scripts and external corpus, not normal CLI jobs. |

Output roots are PROJECT and WORK/Work. Default MCP input root is PROJECT;
--input-root can add explicitly allowed read roots. Relative spec paths resolve
from the process working directory. Paths under /Volumes/NAME automatically
require that volume to be mounted, before creating a directory. Keep symlink and
path-validation checks enabled.

## Default admission and watchdog

| Resource | Before starting | During the job |
|---|---|---|
| System memory pressure | normal | warning/critical/unknown stops the owned job |
| Physical headroom | ≥10 GiB and estimate +8 GiB reserve | <8 GiB stops |
| Swap | Record baseline | >1 GiB growth stops |
| Job footprint | Estimate ≤12 GiB | Sampled total owned footprint >12 GiB stops |
| Boot free space | ≥20 GiB | <15 GiB stops |
| Output volume | Estimated output +15 GiB reserve | Reserve or output budget breach stops |
| Boot used bytes | Optional configured ceiling | Same optional ceiling |
| Process lifetime | Valid deadline/identity | Timeout, cancellation, lost parent or guard failure stops |

The footprint limit is a live watchdog, not an instantaneous kernel allocation
quota. The worker only stops processes belonging to its job. Other applications
are never closed to make room. Partials and diagnostic receipts are retained.

The old private lab also enforced a 400 decimal GB boot-used ceiling. Public 0.6.1
makes that owner-specific ceiling explicit through FFV2_BOOT_USED_LIMIT_BYTES;
free-space, mount and memory defaults remain. Historical reports describe the
original policy used for their measurements, not a rerun of the public code.

The explicit FFV2_IGNORE_SYSTEM_MEMORY=1 or --ignore-system-memory option skips
system pressure/headroom/swap checks for that invocation. It leaves disk, mount,
own-footprint, time and output guards active. Do not place that override in a
normal MCP configuration. The archived lab reports disclose their scoped waiver.
