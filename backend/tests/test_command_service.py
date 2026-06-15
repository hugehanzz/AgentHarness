from app.services.command_service import SAFE_COMMANDS


def test_safe_commands_are_whitelisted():
    assert SAFE_COMMANDS["git_status"] == ["git", "status", "--short"]
    assert SAFE_COMMANDS["git_diff_stat"] == ["git", "diff", "--stat"]
    assert "rm" not in SAFE_COMMANDS
