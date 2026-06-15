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
    assert result.recheck_status == "UNKNOWN"


def test_parse_review_file_uses_current_chinese_sections(tmp_path: Path):
    review = tmp_path / "REVIEW.md"
    review.write_text(
        """# REVIEW.md

## 当前审查任务

本轮复审：员工端手机号验证码登录 + Redis 验证码存储（第二轮）。复审完成，已归档。结论：通过（0 高、0 中、5 低）。

**验证状态：** `mvn test` 通过（158 passed）、`npm run build:h5` 通过。

## 当前待处理问题

本轮中等问题已全部修复，剩余 4 个低优先级问题标记为暂不处理（详见历史归档）。当前无需要 Codex 处理的问题。

## 当前模块复审记录

复审日期：2026-06-09 | 结论：2 中已修复，4 低暂不处理。

## 历史审查归档

- （中）#1 历史中等问题
- （低）#2 历史低优先级问题
""",
        encoding="utf-8",
    )

    result = parse_review_file(str(tmp_path))

    assert result.current_task.startswith("本轮复审")
    assert result.high_count == 0
    assert result.medium_count == 0
    assert result.low_count == 0
    assert result.open_count == 0
    assert result.recheck_status == "PASSED"
    assert result.items == []


def test_parse_review_file_parses_current_chinese_items(tmp_path: Path):
    review = tmp_path / "REVIEW.md"
    review.write_text(
        """# REVIEW.md

## 当前审查任务

本轮审查：登录模块。结论：不通过。

## 当前待处理问题

- [ ] （高）缺少鉴权
- [ ] （中）缺少异常路径测试
- （低）日志级别正式环境需确认，暂不处理

## 历史审查归档

- （高）历史问题不应进入当前列表
""",
        encoding="utf-8",
    )

    result = parse_review_file(str(tmp_path))

    assert result.high_count == 1
    assert result.medium_count == 1
    assert result.low_count == 1
    assert result.open_count == 2
    assert result.recheck_status == "FAILED"
    assert [item.status for item in result.items] == ["OPEN", "OPEN", "WONT_FIX"]


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
