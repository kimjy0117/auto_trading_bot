module.exports = {
  apps: [{
    name: "autotrading",
    script: "uvicorn",
    args: "backend.main:app --host 0.0.0.0 --port 8000",
    interpreter: "python3",
    cron_restart: "50 7 * * 1-5",
    log_date_format: "YYYY-MM-DD HH:mm:ss",
    error_file: "./logs/error.log",
    out_file: "./logs/output.log",
    merge_logs: true,
    max_memory_restart: "500M",
    env: {
      NODE_ENV: "production",
      APP_ENV: "prod"
    }
  }]
};
