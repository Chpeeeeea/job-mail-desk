from job_mail_desk.identity_dictionaries import load_identity_dictionaries
from job_mail_desk.identity_resolver import IdentityCandidate, IdentityResolver
from job_mail_desk.models import ApplicationRecord


def application(
    key: str,
    *,
    company: str = "京东",
    project: str | None = None,
    year: int | None = 2027,
    role: str | None = None,
    job_code: str | None = None,
    business_unit: str | None = None,
) -> ApplicationRecord:
    return ApplicationRecord(
        application_key=key,
        company_key=company,
        company=company,
        recruiting_project=project,
        recruiting_year=year,
        business_unit=business_unit,
        role=role,
        role_aliases=[],
        job_code=job_code,
        submitted_at=None,
        status="active",
        source="test",
        confirmed_by_user=True,
        identity_locked=True,
    )


def resolver() -> IdentityResolver:
    return IdentityResolver(load_identity_dictionaries())


def test_job_code_is_a_strong_match_even_if_role_text_changes() -> None:
    result = resolver().resolve(
        IdentityCandidate(company="百度招聘", role="管培方向", job_code="j101320"),
        [application("baidu-role", company="百度", job_code="J101320", role="管培生")],
    )
    assert result.status == "matched"
    assert result.application_key == "baidu-role"
    assert result.reason == "strong-identifier"


def test_company_only_receipt_never_selects_between_jds_and_tet() -> None:
    result = resolver().resolve(
        IdentityCandidate(company="京东校招", template_id="jd-application-received"),
        [
            application("jds", project="JDS", role="产品经理"),
            application("tet", project="TET", role="TET综合方向"),
        ],
    )
    assert result.status == "unresolved"
    assert result.application_key is None
    assert result.reason == "multiple-candidates"


def test_project_conflict_blocks_cross_linking() -> None:
    result = resolver().resolve(
        IdentityCandidate(
            company="京东",
            recruiting_project="TET",
            role="TET综合方向",
            recruiting_year=2027,
        ),
        [application("jds", project="JDS", role="产品经理")],
    )
    assert result.status == "conflict"
    assert result.application_key is None
    assert "recruiting-project" in result.candidates[0].conflicts


def test_unique_project_and_role_combination_can_match() -> None:
    result = resolver().resolve(
        IdentityCandidate(
            company="京东",
            recruiting_project="JDS新星计划",
            role="产品岗",
            recruiting_year=2027,
        ),
        [
            application("jds", project="JDS", role="产品经理"),
            application("tet", project="TET", role="TET综合方向"),
        ],
    )
    assert result.status == "matched"
    assert result.application_key == "jds"
    assert result.reason == "unique-project-combination"


def test_business_unit_conflict_keeps_netease_units_separate() -> None:
    result = resolver().resolve(
        IdentityCandidate(
            company="网易游戏",
            business_unit="雷火事业群",
            role="产品经理",
        ),
        [
            application(
                "netease-huyu",
                company="网易游戏",
                role="产品经理",
                business_unit="互娱事业群",
            )
        ],
    )
    assert result.status == "conflict"
    assert "business-unit" in result.candidates[0].conflicts


def test_netease_business_unit_and_role_can_match_unique_application() -> None:
    result = resolver().resolve(
        IdentityCandidate(
            company="网易游戏",
            business_unit="雷火事业群",
            role="AI产品经理",
        ),
        [
            application(
                "netease-leihuo",
                company="网易游戏",
                role="AI 产品经理",
                business_unit="雷火事业群",
            ),
            application(
                "netease-huyu",
                company="网易游戏",
                role="产品经理",
                business_unit="互娱事业群",
            ),
        ],
    )
    assert result.status == "matched"
    assert result.application_key == "netease-leihuo"


def test_company_only_single_candidate_is_still_insufficient() -> None:
    result = resolver().resolve(
        IdentityCandidate(company="帆软招聘"),
        [application("fanruan", company="帆软", role="产品经理")],
    )
    assert result.status == "unresolved"
    assert result.reason == "insufficient-identity-evidence"


def test_project_without_year_stays_unresolved_across_two_recruiting_cycles() -> None:
    result = resolver().resolve(
        IdentityCandidate(company="京东", recruiting_project="JDS"),
        [
            application("jds-2027", project="JDS", year=2027),
            application("jds-2028", project="JDS", year=2028),
        ],
    )
    assert result.status == "unresolved"
    assert result.reason == "multiple-candidates"


def test_known_company_never_matches_unknown_company_with_similar_role() -> None:
    result = resolver().resolve(
        IdentityCandidate(company="科大讯飞", role="AI产品经理"),
        [
            application(
                "iflytek",
                company="科大讯飞",
                role="AI 产品经理（J13348）",
            ),
            application(
                "unknown",
                company="未收录科技公司",
                role="AI产品经理",
            ),
        ],
    )
    assert result.status == "matched"
    assert result.application_key == "iflytek"
