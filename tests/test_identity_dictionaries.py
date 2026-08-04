from pathlib import Path

import pytest

from job_mail_desk.identity_dictionaries import (
    DictionaryValidationError,
    load_identity_dictionaries,
)
from job_mail_desk.cli import main


def test_built_in_dictionaries_are_valid() -> None:
    dictionaries = load_identity_dictionaries()
    assert dictionaries.counts() == {
        "companies": 520,
        "programs": 129,
        "roles": 2825,
        "mail_templates": 4,
    }
    assert any(item["id"] == "jd-jds" for item in dictionaries.programs)
    assert any(
        item["id"] == "jd-application-received"
        and item["creates_application"] is False
        for item in dictionaries.mail_templates
    )


def test_user_override_replaces_only_matching_stable_id(tmp_path: Path) -> None:
    (tmp_path / "companies.yml").write_text(
        """version: 1
companies:
  - id: jd
    canonical: 京东
    aliases: [京东校招, 京东零售]
    email_domains: [jd.com]
    business_units: [京东零售]
""",
        encoding="utf-8",
    )
    dictionaries = load_identity_dictionaries(tmp_path)
    jd = next(item for item in dictionaries.companies if item["id"] == "jd")
    assert jd["aliases"] == ["京东校招", "京东零售"]
    assert len(dictionaries.companies) == 520


def test_dictionary_precedence_is_imported_then_legacy_then_manual(
    tmp_path: Path,
) -> None:
    for directory, alias in (
        (tmp_path / "imported", "导入别名"),
        (tmp_path, "旧版人工别名"),
        (tmp_path / "manual", "最终人工别名"),
    ):
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "companies.yml").write_text(
            f"""version: 1
companies:
  - id: jd
    canonical: 京东
    aliases: [{alias}]
    email_domains: [jd.com]
    business_units: []
""",
            encoding="utf-8",
        )
    dictionaries = load_identity_dictionaries(tmp_path)
    jd = next(item for item in dictionaries.companies if item["id"] == "jd")
    assert jd["aliases"] == ["最终人工别名"]


def test_unknown_override_field_fails_closed(tmp_path: Path) -> None:
    (tmp_path / "roles.yml").write_text(
        """version: 1
roles:
  - id: product-manager
    canonical: 产品经理
    aliases: []
    category: 产品
    auto_learn: true
""",
        encoding="utf-8",
    )
    with pytest.raises(DictionaryValidationError, match="未知字段"):
        load_identity_dictionaries(tmp_path)


def test_alias_collision_is_rejected(tmp_path: Path) -> None:
    (tmp_path / "programs.yml").write_text(
        """version: 1
programs:
  - id: jd-jds
    company_id: jd
    canonical: JDS新星计划
    aliases: [JDS]
    recruiting_year: null
  - id: jd-jds-other
    company_id: jd
    canonical: 京东另一项目
    aliases: [JDS]
    recruiting_year: null
""",
        encoding="utf-8",
    )
    with pytest.raises(DictionaryValidationError, match="别名冲突"):
        load_identity_dictionaries(tmp_path)


def test_unknown_company_reference_is_rejected(tmp_path: Path) -> None:
    (tmp_path / "mail_templates.yml").write_text(
        """version: 1
mail_templates:
  - id: unknown-template
    company_id: missing-company
    kind: application_receipt
    subject_patterns: [申请已提交]
    body_patterns: []
    identity_fields: [role]
    creates_application: false
""",
        encoding="utf-8",
    )
    with pytest.raises(DictionaryValidationError, match="未知公司"):
        load_identity_dictionaries(tmp_path)


def test_dictionary_check_returns_structured_failure(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (tmp_path / "roles.yml").write_text(
        "version: 2\nroles: []\n",
        encoding="utf-8",
    )
    assert main(["dictionary-check", "--user-dir", str(tmp_path)]) == 1
    output = capsys.readouterr().out
    assert '"ok": false' in output
    assert "version 必须为 1" in output
