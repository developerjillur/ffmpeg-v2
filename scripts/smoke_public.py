#!/usr/bin/env python3
"""Check an installed CLI and MCP handshake in a fresh media workspace."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--command',default='ffv2')
    args=parser.parse_args()
    parent=Path(__file__).resolve().parents[1]/'.test-work'
    parent.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='public-smoke-',dir=parent) as directory:
        workspace=Path(directory)
        env=dict(os.environ,FFV2_PROJECT_ROOT=str(workspace),FFV2_WORK_ROOT=str(workspace/'scratch'),
                 FFV2_HOST_LOCK=str(workspace/'host.lock'),PYTHONDONTWRITEBYTECODE='1')
        command=str(Path(args.command).resolve()) if '/' in args.command else args.command
        version=subprocess.check_output([command,'--version'],env=env,cwd=workspace,text=True,timeout=10).strip()
        assert version=='0.6.1',version
        messages=[{'jsonrpc':'2.0','id':1,'method':'initialize','params':{'protocolVersion':'2025-11-25','capabilities':{},'clientInfo':{'name':'source-smoke','version':'1'}}},
                  {'jsonrpc':'2.0','method':'notifications/initialized'},
                  {'jsonrpc':'2.0','id':2,'method':'tools/list','params':{}},
                  {'jsonrpc':'2.0','id':3,'method':'ping','params':{}}]
        result=subprocess.run([command,'mcp'],env=env,cwd=workspace,text=True,
            input=''.join(json.dumps(m)+'\n' for m in messages),capture_output=True,timeout=15,check=True)
        responses=[json.loads(line) for line in result.stdout.splitlines()]
        assert [r['id'] for r in responses]==[1,2,3],responses
        assert len(responses[1]['result']['tools'])==8,responses[1]
        assert responses[0]['result']['serverInfo']['version']==version
        generated=subprocess.check_output([os.environ.get('PYTHON','python3'),str(Path(__file__).with_name('configure_local_mcp.py')),
            '--project',str(workspace),'--command',command],env=env,cwd=workspace,text=True,timeout=10)
        config=json.loads(generated)['mcpServers']['ffmpeg-v2']
        assert config['env']['FFV2_PROJECT_ROOT']==str(workspace)
        assert config['command']==command
        print(json.dumps({'status':'passed','version':version,'mcp_tools':8,'fresh_workspace':True,'client_config_printer':True,'media_encode_performed':False}))

if __name__=='__main__':main()
