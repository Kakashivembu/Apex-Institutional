module.exports = {
  apps: [{
    name: 'NVIDIA_APEX',
    script: 'main.py',
    interpreter: './venv/Scripts/python.exe',
    cwd: 'C:/Users/vembu/nvidia_apex_trader',
    watch: false,
    autorestart: true,
    max_memory_restart: '1G'
  }]
};
