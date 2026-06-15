from pathlib import Path

from sqlmodel import Session, SQLModel, create_engine, select

import app.models  # noqa: F401
from app.models.review import ReviewItem
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

## Severity Summary
- High: 9
- Medium: 9
- Low: 9

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


def test_parse_review_replaces_existing_items(tmp_path: Path):
    review = tmp_path / "REVIEW.md"
    review.write_text(
        """# REVIEW.md

## Current Review Task
Implement login module

## Open Issues
- [ ] High: Missing auth guard
- [ ] Medium: Add test coverage
""",
        encoding="utf-8",
    )
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        parse_review_file(str(tmp_path), session=session, task_id=1)
        parse_review_file(str(tmp_path), session=session, task_id=1)

        items = session.exec(select(ReviewItem).where(ReviewItem.task_id == 1)).all()
        assert len(items) == 2
