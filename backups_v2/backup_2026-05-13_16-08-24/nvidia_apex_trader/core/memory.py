import os

MEMORY_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'APEX_MEMORY.md')

def load_memory() -> str:
    if not os.path.exists(MEMORY_FILE):
        return "No memory found."
    with open(MEMORY_FILE, 'r') as f:
        return f.read()

def append_to_memory(new_rule: str):
    with open(MEMORY_FILE, 'a') as f:
        f.write(f"\n- **NEW LESSON:** {new_rule}")

