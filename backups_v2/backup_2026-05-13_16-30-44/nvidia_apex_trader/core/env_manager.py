import os
import dotenv

ENV_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env')

AI_ROLES = {
    "chat": "NVIDIA_CHAT_KEY",
    "fundamental": "OPENROUTER_API_KEY",
    "scalper": "NVIDIA_API_KEY",
    "trend": "NVIDIA_API_KEY_2"
}

def get_ai_keys():
    dotenv.load_dotenv(ENV_PATH, override=True)
    return {
        "chat": os.getenv("NVIDIA_CHAT_KEY", ""),
        "fundamental": os.getenv("OPENROUTER_API_KEY", ""),
        "scalper": os.getenv("NVIDIA_API_KEY", ""),
        "trend": os.getenv("NVIDIA_API_KEY_2", "")
    }

def update_ai_key(role: str, key: str):
    env_var = AI_ROLES.get(role)
    if env_var:
        # Create file if it doesn't exist
        if not os.path.exists(ENV_PATH):
            open(ENV_PATH, 'a').close()
            
        dotenv.set_key(ENV_PATH, env_var, key)
        refresh_in_memory_keys()
        return True
    return False

def delete_ai_key(role: str):
    env_var = AI_ROLES.get(role)
    if env_var:
        dotenv.unset_key(ENV_PATH, env_var)
        refresh_in_memory_keys()
        return True
    return False

def refresh_in_memory_keys():
    dotenv.load_dotenv(ENV_PATH, override=True)
    
    # Safely update the AI agent's memory
    try:
        import core.brain
        core.brain.NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY", "")
        core.brain.NVIDIA_API_KEY_2 = os.getenv("NVIDIA_API_KEY_2", "")
        core.brain.OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
        
        core.brain.NVIDIA_KEYS = [k for k in [core.brain.NVIDIA_API_KEY, core.brain.NVIDIA_API_KEY_2] if k]
    except ImportError:
        pass

# ── GLOBAL MARKET DATA KEYS (Split-Brain Architecture) ──
# These keys are used exclusively for READ-ONLY mainnet data fetching.
# They are never used for trade execution.

def get_data_keys():
    """Return the Global Market Data API Key/Secret from .env (masked)."""
    dotenv.load_dotenv(ENV_PATH, override=True)
    return {
        "api_key": os.getenv("DELTA_DATA_KEY", ""),
        "api_secret": os.getenv("DELTA_DATA_SECRET", "")
    }

def update_data_keys(api_key: str, api_secret: str):
    """Write the Global Market Data API Key/Secret to .env."""
    if not os.path.exists(ENV_PATH):
        open(ENV_PATH, 'a').close()
    dotenv.set_key(ENV_PATH, "DELTA_DATA_KEY", api_key)
    dotenv.set_key(ENV_PATH, "DELTA_DATA_SECRET", api_secret)
    dotenv.load_dotenv(ENV_PATH, override=True)
    return True

def delete_data_keys():
    """Remove the Global Market Data API Key/Secret from .env."""
    dotenv.unset_key(ENV_PATH, "DELTA_DATA_KEY")
    dotenv.unset_key(ENV_PATH, "DELTA_DATA_SECRET")
    dotenv.load_dotenv(ENV_PATH, override=True)
    return True
