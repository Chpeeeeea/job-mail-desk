from job_mail_desk.dictionary_compiler import compile_rows
from job_mail_desk.identity_dictionaries import load_identity_dictionaries


def test_compile_rows_separates_company_project_and_exact_roles() -> None:
    rows = [
        ["招聘类型", "公司及项目名称", "职位名称"],
        ["2027届秋招", "海信集团【信动力计划】", "产品经理;算法工程师;暑期开放日"],
        ["27届提前批", "睿创微纳【追光者】", "实时嵌入式软件工程师测试岗；可靠性质量工程师测试样例"],
    ]
    result = compile_rows(rows, load_identity_dictionaries())
    companies = result["companies"]
    programs = result["programs"]
    roles = result["roles"]
    assert any(item["id"] == "hisense" for item in companies)
    assert {item["canonical"] for item in programs} == {"信动力计划", "追光者"}
    assert "暑期开放日" in result["skipped_non_roles"]
    assert any(
        item["canonical"] == "实时嵌入式软件工程师测试岗"
        and item["category"] == "软件研发"
        for item in roles
    )
    assert any(
        item["canonical"] == "可靠性质量工程师测试样例"
        and item["category"] == "测试与质量"
        for item in roles
    )


def test_compile_rows_does_not_merge_similar_company_names() -> None:
    rows = [
        ["招聘类型", "公司及项目名称", "职位名称"],
        ["2027届秋招", "网易雷火【专项计划】", "产品经理"],
        ["2027届秋招", "网易互娱【专项计划】", "产品经理"],
    ]
    result = compile_rows(rows, load_identity_dictionaries())
    assert len(result["companies"]) == 2
    assert len({item["company_id"] for item in result["programs"]}) == 2


def test_compile_rows_reuses_reviewed_program_identity() -> None:
    rows = [
        ["招聘类型", "公司及项目名称", "职位名称"],
        ["2027届秋招", "京东【TET】", "管培生"],
    ]
    result = compile_rows(rows, load_identity_dictionaries())
    assert len(result["programs"]) == 1
    assert result["programs"][0]["id"] == "jd-tet"
    assert result["programs"][0]["canonical"] == "TET管培生计划"
