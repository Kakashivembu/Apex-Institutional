import json
from graphify.detect import detect
from pathlib import Path

result = detect(Path('.'))
Path('graphify-out/.graphify_detect.json').write_text(json.dumps(result))
print(f"total_files: {result['total_files']}, total_words: {result['total_words']}")
for k, v in result.get('files', {}).items():
    if v:
        print(f"  {k}: {len(v)} files")
