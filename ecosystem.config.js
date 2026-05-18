module.exports = {
  apps: [
    {
      name: "Apex-Frontend",
      cwd: "./frontend",
      script: "./node_modules/vite/bin/vite.js",
      args: "--host",
      interpreter: "node",
      max_restarts: 10,
      restart_delay: 3000,
      max_memory_restart: "512M",
      kill_timeout: 5000,
      treekill: true,
      merge_logs: true,
      out_file: "./logs/frontend-out.log",
      error_file: "./logs/frontend-error.log",
      env: {
        NODE_OPTIONS: "--no-warnings --max-old-space-size=512"
      }
    },
    {
      name: "Apex-Backend",
      cwd: "./nvidia_apex_trader",
      script: "python",
      args: "-u -m uvicorn server:app --host 0.0.0.0 --port 8000 --no-access-log",
      interpreter: "none",
      max_restarts: 10,
      restart_delay: 5000,
      max_memory_restart: "1G",
      kill_timeout: 8000,
      treekill: true,
      merge_logs: true,
      out_file: "./logs/backend-out.log",
      error_file: "./logs/backend-error.log",
      env: {
        PYTHONUNBUFFERED: "1"
      }
    }
  ]
};