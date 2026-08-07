# Data Collector

## Configuration

All deployment-specific configuration is read from the untracked `.env` file.
Create it before starting the stack:

```powershell
Copy-Item .env.example .env
```

Replace every `CHANGE_ME` value, then start the services with Docker Compose.
Application code intentionally fails fast when a required environment variable
is missing instead of silently using a hardcoded credential, host, or port.
