# AgentHarness Backend

FastAPI backend for the AgentHarness local multi-agent workflow controller.

## Conda Setup

```bash
conda create -n agentharness python=3.11 -y
conda activate agentharness
cd backend
pip install -e ".[dev]"
```

Or:

```bash
conda env create -f environment.yml
conda activate agentharness
```

## Configuration

Copy `.env.example` to `.env` and update `DATABASE_URL`.

```env
DATABASE_URL=mysql+pymysql://agentharness:agentharness@localhost:3306/agentharness
```

Create the MySQL database before first run:

```sql
CREATE DATABASE agentharness CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'agentharness'@'localhost' IDENTIFIED BY 'agentharness';
GRANT ALL PRIVILEGES ON agentharness.* TO 'agentharness'@'localhost';
FLUSH PRIVILEGES;
```

## Run

```bash
uvicorn app.main:app --reload
```

## Test

```bash
pytest
```

Tests use SQLite in memory and do not require MySQL.
