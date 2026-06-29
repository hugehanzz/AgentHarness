-- Seed AgentHarness built-in workers.
-- status 和 last_heartbeat_at 是运行时状态，初始化时统一置为 OFFLINE / NULL，
-- 后端启动后的心跳检查会自动更新为 ONLINE / RUNNING / FAILED。

INSERT INTO agentworker
    (worker_key, name, role, provider_type, status, last_heartbeat_at)
VALUES
    ('codex',  'Codex',  'Developer',   'codex_app_server', 'OFFLINE', NULL),
    ('claude', 'Claude', 'Reviewer',    'claude_cli',       'OFFLINE', NULL),
    ('gemini', 'Gemini', 'Coordinator', 'gemini_api',       'OFFLINE', NULL)
ON DUPLICATE KEY UPDATE
    worker_key = worker_key;