import asyncio, subprocess, os
async def test():
    with open('test_prompt.txt', 'w', encoding='utf-8') as f:
        f.write('Line 1\nLOW,dominant_side:LONG:\nLine 3')
    
    cmd = 'P=$(cat test_prompt.txt); echo "$P"'
    process = await asyncio.create_subprocess_exec('wsl.exe', 'python3', '-c', 'import sys; print(sys.argv)', '-c', cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    stdout, stderr = await asyncio.wait_for(process.communicate(), 60)
    print('OUT:', stdout.decode('utf-8'))
    print('ERR:', stderr.decode('utf-8'))
asyncio.run(test())
