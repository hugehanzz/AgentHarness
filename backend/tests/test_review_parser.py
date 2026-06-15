from pathlib import Path

from app.services.review_parser import parse_review_file


def test_parse_review_file(tmp_path: Path):
    review = tmp_path / "REVIEW.md"
    review.write_text(
        """# REVIEW.md

## Current Review Task
Implement login module

## Open Issues
- [ ] High: Missing auth guard
- [ ] Medium: Add test coverage
- [x] Low: Typo fixed

## Recheck Conclusion
UNKNOWN
""",
        encoding="utf-8",
    )

    result = parse_review_file(str(tmp_path))

    assert result.current_task == "Implement login module"
    assert result.high_count == 1
    assert result.medium_count == 1
    assert result.low_count == 1
    assert result.open_count == 2
