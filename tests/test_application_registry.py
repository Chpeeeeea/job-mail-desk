from datetime import datetime

import pytest

from job_mail_desk.application_registry import (
    ApplicationRegistry,
    application_from_progress_entry,
    preview_progress_applications,
    stable_application_key,
)
from job_mail_desk.models import ApplicationRecord
from job_mail_desk.parser import SHANGHAI


def test_job_code_is_strong_stable_identity() -> None:
    first = stable_application_key(
        company="百度",
        role="2027 管培生（J101320）",
        recruiting_project=None,
        recruiting_year=2027,
        business_unit=None,
        job_code="J101320",
        legacy_application_id=None,
    )
    renamed = stable_application_key(
        company="百度招聘",
        role="北京-2027管培生",
        recruiting_project="校园招聘",
        recruiting_year=2027,
        business_unit=None,
        job_code="j101320",
        legacy_application_id="different-legacy-id",
    )
    assert first == renamed


def test_progress_entry_becomes_locked_application() -> None:
    record = application_from_progress_entry(
        {
            "company": "京东",
            "role": "2027 JDS 新星计划-产研项目管理",
            "project": "",
            "status": "简历已投递，等待筛选",
            "action": "2026-08-03 完成投递",
            "application_id": "a" * 20,
        },
        now=datetime(2026, 8, 3, 20, 0, tzinfo=SHANGHAI),
    )
    assert record is not None
    assert record.recruiting_project == "JDS"
    assert record.recruiting_year == 2027
    assert record.role == "2027 JDS 新星计划-产研项目管理"
    assert record.submitted_at == datetime(2026, 8, 3, tzinfo=SHANGHAI)
    assert record.identity_locked is True
    assert record.legacy_application_ids == ["a" * 20]


def test_event_date_does_not_become_recruiting_year() -> None:
    record = application_from_progress_entry(
        {
            "company": "京东",
            "role": "TET 综合方向",
            "project": "",
            "status": "群面已安排",
            "action": "2026-08-06 参加群面",
            "application_id": "b" * 20,
        }
    )
    assert record is not None
    assert record.recruiting_year is None
    assert "recruiting-year-unresolved" in record.identity_evidence


def test_registry_round_trip_and_locked_import_is_idempotent(tmp_path) -> None:
    ledger = tmp_path / "ledger.md"
    ledger.write_text(
        """# 台账

### 已投递或已进入流程

- [x] 百度｜2027 管培生（J101320）｜**已投递**｜等待后续 <!-- jobmaildesk:application:11111111111111111111 -->
""",
        encoding="utf-8",
    )
    registry = ApplicationRegistry(tmp_path / "applications")
    first = registry.import_progress(ledger)
    second = registry.import_progress(ledger)
    assert len(first) == len(second) == 1
    assert first[0].application_key == second[0].application_key
    loaded = registry.load(first[0].application_key)
    assert loaded is not None
    assert loaded.job_code == "J101320"
    assert loaded.identity_locked is True


def test_preview_deduplicates_same_identity(tmp_path) -> None:
    ledger = tmp_path / "ledger.md"
    ledger.write_text(
        """# 台账

### 已投递或已进入流程

- [x] 科大讯飞｜AI 产品经理（J13348）｜**已投递**｜等待测评
- [x] 讯飞招聘｜AI产品经理 J13348｜**测评完成**｜等待后续
""",
        encoding="utf-8",
    )
    records = preview_progress_applications(ledger)
    assert len(records) == 1
    assert records[0].company == "科大讯飞"
    assert records[0].job_code == "J13348"


def test_duplicate_identity_merges_terminal_status(tmp_path) -> None:
    ledger = tmp_path / "ledger.md"
    ledger.write_text(
        """# 台账

### 已投递或已进入流程
- [x] 百度｜2027 管培生（J101320）｜**已投递**｜等待后续
- [x] 百度招聘｜管培生 J101320｜**未通过**｜流程结束
""",
        encoding="utf-8",
    )
    records = preview_progress_applications(ledger)
    assert len(records) == 1
    assert records[0].status == "ended"


def test_offer_is_terminal_in_identity_registry(tmp_path) -> None:
    ledger = tmp_path / "ledger.md"
    ledger.write_text(
        """# 台账

### 已投递或已进入流程
- [x] 帆软｜产品经理｜**2026-09-04 已 Offer**｜等待入职
""",
        encoding="utf-8",
    )

    records = preview_progress_applications(ledger)
    assert len(records) == 1
    assert records[0].status == "ended"

    ledger.write_text(
        """# 台账

### 已投递或已进入流程
- [x] 帆软｜产品经理｜**等待 Offer 审批**｜等待结果
""",
        encoding="utf-8",
    )
    assert preview_progress_applications(ledger)[0].status == "active"


def test_unidentified_placeholder_row_is_not_locked_or_imported(tmp_path) -> None:
    ledger = tmp_path / "ledger.md"
    ledger.write_text(
        """# 台账

### 已投递或已进入流程
- [ ] 公司待确认｜｜待确认｜等待补充
""",
        encoding="utf-8",
    )
    assert preview_progress_applications(ledger) == []


def test_netease_business_unit_survives_progress_normalization(tmp_path) -> None:
    ledger = tmp_path / "ledger.md"
    ledger.write_text(
        """# 台账

### 已投递或已进入流程
- [x] 网易雷火｜产品经理｜已投递｜等待后续
""",
        encoding="utf-8",
    )
    records = preview_progress_applications(ledger)
    assert len(records) == 1
    assert records[0].company == "网易游戏"
    assert records[0].business_unit == "雷火事业群"


def test_registry_all_raises_on_corrupt_application(tmp_path) -> None:
    applications = tmp_path / "applications"
    applications.mkdir()
    (applications / "app-deadbeefdeadbeefdeadbeef.md").write_text(
        "not frontmatter",
        encoding="utf-8",
    )
    registry = ApplicationRegistry(applications)
    with pytest.raises(ValueError, match="frontmatter"):
        registry.all()
    assert registry.all(ignore_invalid=True) == []


def test_application_record_rejects_string_boolean(tmp_path) -> None:
    applications = tmp_path / "applications"
    registry = ApplicationRegistry(applications)
    record = application_from_progress_entry(
        {
            "company": "帆软",
            "role": "产品经理",
            "project": "",
            "status": "已投递",
            "action": "",
            "application_id": "c" * 20,
        }
    )
    assert record is not None
    path = registry.save(record)
    content = path.read_text(encoding="utf-8").replace(
        "identity_locked: true",
        "identity_locked: 'false'",
    )
    path.write_text(content, encoding="utf-8")
    with pytest.raises(ValueError, match="identity_locked"):
        registry.load(record.application_key)


def test_application_record_rejects_string_role_aliases_and_boolean_year() -> None:
    payload = {
        "application_key": "app-" + "d" * 24,
        "company_key": "demo",
        "company": "示例公司",
        "recruiting_project": None,
        "recruiting_year": True,
        "business_unit": None,
        "role": "产品经理",
        "role_aliases": "产品岗",
        "job_code": None,
        "submitted_at": None,
        "status": "active",
        "source": "test",
        "confirmed_by_user": True,
        "identity_locked": True,
        "legacy_application_ids": [],
        "identity_evidence": [],
    }
    with pytest.raises(ValueError, match="recruiting_year"):
        ApplicationRecord.from_dict(payload)
    payload["recruiting_year"] = 2027
    with pytest.raises(ValueError, match="role_aliases"):
        ApplicationRecord.from_dict(payload)


def test_generic_company_and_invalid_role_are_not_imported(tmp_path) -> None:
    ledger = tmp_path / "ledger.md"
    ledger.write_text(
        """# 台账

### 已投递或已进入流程
- [ ] 招聘｜产品经理｜待确认｜等待补充
- [ ] 示例公司｜点击官网进行修改｜待确认｜等待补充
""",
        encoding="utf-8",
    )
    assert preview_progress_applications(ledger) == []


def test_locked_import_refreshes_terminal_status_without_rewriting_identity(
    tmp_path,
) -> None:
    ledger = tmp_path / "ledger.md"
    ledger.write_text(
        """# 台账

### 已投递或已进入流程
- [x] 百度｜2027 管培生（J101320）｜**已投递**｜等待后续
""",
        encoding="utf-8",
    )
    registry = ApplicationRegistry(tmp_path / "applications")
    first = registry.import_progress(ledger)[0]
    ledger.write_text(
        """# 台账

### 已投递或已进入流程
- [x] 百度招聘｜管培生 J101320｜**未通过**｜流程结束
""",
        encoding="utf-8",
    )
    updated = registry.import_progress(ledger)[0]
    assert updated.application_key == first.application_key
    assert updated.status == "ended"
    assert updated.company == first.company
