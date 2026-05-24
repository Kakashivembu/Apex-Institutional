import asyncio, subprocess
async def test():
    with open('test_crlf.sh', 'w', encoding='utf-8') as f:
        f.write('#!/bin/bash\nP="hello"\npython3 -c "import sys; print(sys.argv)" -z "$P"\n')
    
    process = await asyncio.create_subprocess_exec('wsl.exe', 'bash', 'test_crlf.sh', stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    stdout, stderr = await asyncio.wait_for(process.communicate(), 60)
    print('OUT:', stdout.decode('utf-8'))
    print('ERR:', stderr.decode('utf-8'))
asyncio.run(test())
