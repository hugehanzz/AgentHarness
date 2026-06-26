from pathlib import Path

import pytest
from fastapi import HTTPException
from sqlmodel import Session, SQLModel, create_engine, select

import app.models  # noqa: F401
from app.models.review import ReviewItem
from app.services.review_parser import parse_review_file


def test_parse_review_file_uses_machine_json(tmp_path: Path):
    review = tmp_path / "REVIEW.md"
    review.write_text(
        """# REVIEW.md

## 维护规则

由 Claude-DeepSeek 维护。

## 机器可读状态

```json
{
  "schema_version": 1,
  "current_task": "员工端手机号验证码登录 + Redis 验证码存储",
  "review_status": "ARCHIVED",
  "recheck_status": "PASSED",
  "needs_codex_action": false,
  "summary": "复审通过，当前无需要 Codex 处理的问题。",
  "issue_counts": {
    "HIGH": 0,
    "MEDIUM": 0,
    "LOW": 5
  },
  "issues": [
    {
      "id": "LOW-3",
      "severity": "LOW",
      "status": "WONT_FIX",
      "title": "验证码 INFO 级别日志，正式环境有泄露风险",
      "description": "后续接入真实短信服务时调整。"
    }
  ]
}
```

## 当前审查任务

这里的正文可以给人阅读。
""",
        encoding="utf-8",
    )

    result = parse_review_file(str(tmp_path))

    assert result.current_task == "员工端手机号验证码登录 + Redis 验证码存储"
    assert result.high_count == 0
    assert result.medium_count == 0
    assert result.low_count == 5
    assert result.open_count == 0
    assert result.recheck_status == "PASSED"
    assert len(result.items) == 1
    assert result.items[0].status == "WONT_FIX"


def test_parse_review_file_counts_open_machine_json_items(tmp_path: Path):
    review = tmp_path / "REVIEW.md"
    review.write_text(
        """# REVIEW.md

## 机器可读状态

```json
{
  "schema_version": 1,
  "current_task": "登录模块",
  "review_status": "FIX_REQUIRED",
  "recheck_status": "PENDING",
  "needs_codex_action": true,
  "summary": "仍有问题需要处理。",
  "issue_counts": {
    "HIGH": 1,
    "MEDIUM": 1,
    "LOW": 1
  },
  "issues": [
    {
      "id": "HIGH-1",
      "severity": "HIGH",
      "status": "OPEN",
      "title": "缺少鉴权"
    },
    {
      "id": "MEDIUM-1",
      "severity": "MEDIUM",
      "status": "FIXED_PENDING_RECHECK",
      "title": "异常路径测试待复审"
    },
    {
      "id": "LOW-1",
      "severity": "LOW",
      "status": "CLOSED",
      "title": "文案已关闭"
    }
  ]
}
```
""",
        encoding="utf-8",
    )

    result = parse_review_file(str(tmp_path))

    assert result.high_count == 1
    assert result.medium_count == 1
    assert result.low_count == 1
    assert result.open_count == 2
    assert [item.status for item in result.items] == ["OPEN", "FIXED_PENDING_RECHECK", "CLOSED"]


def test_parse_review_file_rejects_invalid_machine_json(tmp_path: Path):
    review = tmp_path / "REVIEW.md"
    review.write_text(
        """# REVIEW.md

## 机器可读状态

```json
{
  "schema_version": 1,
}
```

## 当前审查任务

不要 fallback 到正文猜测。
""",
        encoding="utf-8",
    )

    with pytest.raises(HTTPException) as exc_info:
        parse_review_file(str(tmp_path))

    assert exc_info.value.status_code == 422
    assert "Invalid REVIEW.md machine JSON" in exc_info.value.detail


def test_parse_review_file_reports_machine_json_line_for_unescaped_quote(tmp_path: Path):
    review = tmp_path / "REVIEW.md"
    review.write_text(
        """# REVIEW.md

## 机器可读状态

```json
{
  "schema_version": 1,
  "current_task": "快速排序",
  "review_status": "FIX_REQUIRED",
  "recheck_status": "NOT_REQUIRED",
  "needs_codex_action": true,
  "summary": "发现问题",
  "issue_counts": {
    "HIGH": 1,
    "MEDIUM": 0,
    "LOW": 0
  },
  "issues": [
    {
      "id": "HIGH-1",
      "severity": "HIGH",
      "status": "OPEN",
      "title": "缺少测试",
      "description": "需求要求"新增一个Test"，但没有添加 @Test 方法。"
    }
  ]
}
```
""",
        encoding="utf-8",
    )

    with pytest.raises(HTTPException) as exc_info:
        parse_review_file(str(tmp_path))

    assert exc_info.value.status_code == 422
    assert "Invalid REVIEW.md machine JSON at line" in exc_info.value.detail
    assert "未转义英文双引号" in exc_info.value.detail
    assert "description" in exc_info.value.detail


def test_parse_review_file_repairs_chinese_structural_quotes(tmp_path: Path):
    review = tmp_path / "REVIEW.md"
    review.write_text(
        """# REVIEW.md

## 机器可读状态

```json
{
  “schema_version”: 1,
  “current_task”: “快速排序”,
  “review_status”: “FIX_REQUIRED”,
  “recheck_status”: “FAILED”,
  “needs_codex_action”: true,
  “summary”: “复审未通过，需要继续修复。”,
  “issue_counts”: {
    “HIGH”: 1,
    “MEDIUM”: 0,
    “LOW”: 0
  },
  “issues”: [
    {
      “id”: “HIGH-1”,
      “severity”: “HIGH”,
      “status”: “OPEN”,
      “title”: “缺少测试”,
      “description”: “需求要求“新增一个Test”，但没有添加 @Test 方法。”
    }
  ]
}
```
""",
        encoding="utf-8",
    )

    result = parse_review_file(str(tmp_path))

    assert result.current_task == "快速排序"
    assert result.high_count == 1
    assert result.open_count == 1
    assert result.recheck_status == "FAILED"
    assert result.items[0].description == "需求要求“新增一个Test”，但没有添加 @Test 方法。"


def test_parse_review_file_falls_back_to_markdown_without_machine_json(tmp_path: Path):
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
    assert result.recheck_status == "PENDING"


def test_parse_review_file_replaces_existing_items(tmp_path: Path):
    review = tmp_path / "REVIEW.md"
    review.write_text(
        """# REVIEW.md

## 机器可读状态

```json
{
  "schema_version": 1,
  "current_task": "登录模块",
  "review_status": "FIX_REQUIRED",
  "recheck_status": "PENDING",
  "needs_codex_action": true,
  "summary": "仍有问题需要处理。",
  "issue_counts": {
    "HIGH": 1,
    "MEDIUM": 0,
    "LOW": 0
  },
  "issues": [
    {
      "id": "HIGH-1",
      "severity": "HIGH",
      "status": "FIXED_PENDING_RECHECK",
      "title": "缺少鉴权"
    }
  ]
}
```
""",
        encoding="utf-8",
    )
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        parse_review_file(str(tmp_path), session=session, task_id=1)
        parse_review_file(str(tmp_path), session=session, task_id=1)

        items = session.exec(select(ReviewItem).where(ReviewItem.task_id == 1)).all()
        assert len(items) == 1
        assert items[0].status == "FIXED_PENDING_RECHECK"
