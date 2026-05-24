import asyncio, subprocess, uuid
async def test():
    prompt_filename = f".hermes_prompt_{uuid.uuid4().hex[:8]}.txt"
    with open(prompt_filename, "w", encoding="utf-8") as f:
        f.write("Line 1\nLine 2")
        
    script_filename = f".hermes_run_{uuid.uuid4().hex[:8]}.sh"
    prov_flag = ""
    script_content = f'''#!/bin/bash
P=$(cat {prompt_filename})
echo "OUTPUT: $P"
'''
    with open(script_filename, "w", encoding="utf-8") as f:
        f.write(script_content)
        
    wsl_cmd = ["wsl.exe", "bash", script_filename]
    process = await asyncio.create_subprocess_exec(
        *wsl_cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=120.0)
    print("RETURN CODE:", process.returncode)
    output_text = stdout.decode('utf-8', errors='replace').strip()
    err_text = stderr.decode('utf-8', errors='replace').strip()
    print('OUT:', repr(output_text))
    print('ERR:', repr(err_text))
asyncio.run(test())
