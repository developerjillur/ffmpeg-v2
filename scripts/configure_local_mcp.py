#!/usr/bin/env python3
"""Print a client-neutral MCP configuration without editing client settings."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import shutil

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', required=True, type=Path, help='Existing media workspace to allow')
    parser.add_argument('--work-root', type=Path, help='Optional large-data workspace')
    parser.add_argument('--command', default=shutil.which('ffv2') or 'ffv2', help='Absolute installed ffv2 command recommended')
    args = parser.parse_args()
    project = args.project.expanduser().resolve(strict=True)
    if not project.is_dir():
        parser.error('--project must be an existing directory')
    env = {'FFV2_PROJECT_ROOT': str(project)}
    if args.work_root:
        env['FFV2_WORK_ROOT'] = str(args.work_root.expanduser().absolute())
    print(json.dumps({'mcpServers': {'ffmpeg-v2': {'command': args.command,
        'args': ['--input-root', str(project), 'mcp'], 'env': env}}}, indent=2))
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
