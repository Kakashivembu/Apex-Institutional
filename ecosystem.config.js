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
    },
    {
      name: "Apex-CBT-Analyzer",
      cwd: "./",
      script: "generate_cbt_report.bat",
      interpreter: "cmd.exe",
      instances: 1,
      exec_mode: "fork",
      cron_restart: "0 0 * * *", // Run at midnight every day
      autorestart: false,        // Don't auto-restart after it finishes running
      merge_logs: true,
      out_file: "./logs/cbt-out.log",
      error_file: "./logs/cbt-error.log"
    },
    {
      name: "Apex-Forge-Proxy",
      cwd: "./",
      script: "python",
      args: "-u -m forge.proxy --backend-url https://integrate.api.nvidia.com/v1 --backend-protocol openai --budget-mode manual --budget-tokens 32768",
      interpreter: "none",
      max_restarts: 10,
      restart_delay: 5000,
      merge_logs: true,
      out_file: "./logs/forge-out.log",
      error_file: "./logs/forge-error.log",
      env: {
        PYTHONUNBUFFERED: "1",
        OPENAI_API_KEY: "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",
        NVIDIA_API_KEY: "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"
      }
    }
  ]
};