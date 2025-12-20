module.exports = {
  apps: [
    {
      name: 'agrawal-backend',
      cwd: './backend',
      script: 'venv/bin/python',
      args: '-m uvicorn app.main:app --host 0.0.0.0 --port 8000',
      interpreter: 'none',
      env: {
        PATH: process.env.PATH
      },
      watch: false,
      autorestart: true,
      max_restarts: 10,
    },
    {
      name: 'agrawal-frontend',
      cwd: './frontend',
      script: 'npm',
      args: 'run dev',
      interpreter: 'none',
      env: {
        PATH: process.env.PATH
      },
      watch: false,
      autorestart: true,
      max_restarts: 10,
    }
  ]
};

