from __future__ import annotations

import hashlib
import json
import re
import unicodedata
import zipfile
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable
from xml.etree import ElementTree

import yaml

from .identity_dictionaries import IdentityDictionaries
from .markdown_store import _atomic_write


MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
DOC_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
MAX_WORKBOOK_BYTES = 50 * 1024 * 1024
MAX_UNCOMPRESSED_BYTES = 200 * 1024 * 1024
MAX_ROWS = 100_000
PROJECT = re.compile(r"【(?P<project>[^】]+)】")
ROLE_SPLIT = re.compile(r"[;；\n]+")
NON_ROLE = re.compile(
    r"开放日$|夏令营$|实践活动$|创变营$|"
    r"^(?:详见|查看|点击).*(?:官网|公告)$|"
    r"^(?:多个|若干|全部|各类)岗位$|^岗位待定$"
)

ROLE_FAMILIES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("产品", re.compile(r"产品|用户体验|产品企划")),
    ("项目管理", re.compile(r"项目管理|项目经理|PMO|交付管理", re.I)),
    ("算法与人工智能", re.compile(r"算法|人工智能|机器学习|深度学习|大模型|计算机视觉|自然语言", re.I)),
    ("数据", re.compile(r"数据分析|数据开发|数据科学|数据工程|商业分析|BI\b", re.I)),
    ("软件研发", re.compile(r"软件|开发工程师|前端|后端|客户端|Android|iOS|Java|C\+\+|运维|DevOps", re.I)),
    ("嵌入式与硬件", re.compile(r"嵌入式|硬件|电子|电气|射频|通信|固件")),
    ("集成电路与半导体", re.compile(r"IC|芯片|半导体|版图|验证工程师|器件|FPGA|ASIC|EDA", re.I)),
    ("机械与结构", re.compile(r"机械|结构|机电|车辆|底盘|动力|热管理|工业设计")),
    ("材料化学与光电", re.compile(r"材料|化学|光学|光电|激光|晶体|封装")),
    ("仿真与控制", re.compile(r"仿真|控制工程|CAE|CAD|CAM|建模与仿真", re.I)),
    ("测试与质量", re.compile(r"测试|质量|可靠性|失效分析|质保|QA\b|QC\b", re.I)),
    ("制造与工艺", re.compile(r"制造|工艺|设备|生产|厂务|IE\b|精益", re.I)),
    ("销售与商务", re.compile(r"销售|商务|客户经理|渠道|售前|售后|解决方案")),
    ("市场与运营", re.compile(r"市场|品牌|运营|内容|新媒体|公关|传播|用户增长")),
    ("供应链与采购", re.compile(r"供应链|采购|物流|仓储|计划|供应商")),
    ("金融与投资", re.compile(r"投资|投行|证券|量化|交易|研究员|银行|保险|精算|财富管理")),
    ("财务审计与风控", re.compile(r"财务|会计|审计|税务|风控|合规")),
    ("人力与综合职能", re.compile(r"人力|招聘|行政|法务|纪检|党群|综合职能|秘书")),
    ("安全与环境", re.compile(r"信息安全|网络安全|攻防|安全工程|EHS|环境工程|HSE", re.I)),
    ("设计与创意", re.compile(r"设计师|视觉设计|交互设计|体验设计|动画|美术|建模师|CMF|创意策划|视频|剪辑", re.I)),
    ("技术服务与交付", re.compile(r"应用工程师|FAE|AE/|AE工程师|技术支持|客户服务|交付工程师|实施工程师|服务工程师", re.I)),
    ("系统与架构", re.compile(r"架构工程师|系统工程师|系统研发|Infra|基础架构|基础设施", re.I)),
    ("科研与研发", re.compile(r"科学家|研究助理|研究岗|研发工程师|技术研发|研发类|技术类")),
    ("国际与贸易", re.compile(r"国际业务|海外业务|外贸|军贸|国际贸易")),
    ("咨询", re.compile(r"咨询|顾问")),
    ("建筑与工程", re.compile(r"建筑|土木|工程管理|造价|给排水|暖通|施工")),
    ("生物医药", re.compile(r"生物|医药|医学|临床|药物|制剂|CRA\b", re.I)),
    ("教育", re.compile(r"教师|教研|课程|辅导|教育")),
    ("管理培训", re.compile(r"管培|管理培训|储备干部|储备经理")),
    ("游戏与数字内容", re.compile(r"游戏|关卡|数值策划|剧情策划|音频|特效|导演")),
    ("实习与人才培养", re.compile(r"实习生|培养对象|培训生|技培生|见习生")),
    ("工程技术/待细分", re.compile(r"工程师|工程岗|工程类|技术岗|技术类|研发|开发$|控制$")),
    ("业务管理/待细分", re.compile(r"业务|管理|专员|助理|经理|分析师|策划")),
)


def _token(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value)
    return re.sub(r"\s+", "", normalized).casefold()


def _stable_id(prefix: str, *values: str) -> str:
    payload = "|".join(_token(value) for value in values)
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
    return f"local-{prefix}-{digest}"


def _column_index(reference: str) -> int:
    letters = "".join(character for character in reference if character.isalpha())
    result = 0
    for character in letters.upper():
        result = result * 26 + ord(character) - ord("A") + 1
    return result - 1


def _shared_strings(archive: zipfile.ZipFile) -> list[str]:
    path = "xl/sharedStrings.xml"
    if path not in archive.namelist():
        return []
    root = ElementTree.fromstring(archive.read(path))
    return [
        "".join(node.text or "" for node in item.findall(f".//{{{MAIN_NS}}}t"))
        for item in root.findall(f"{{{MAIN_NS}}}si")
    ]


def _sheet_path(archive: zipfile.ZipFile, sheet_name: str) -> str:
    workbook = ElementTree.fromstring(archive.read("xl/workbook.xml"))
    relation_id: str | None = None
    for sheet in workbook.findall(f".//{{{MAIN_NS}}}sheet"):
        if sheet.attrib.get("name") == sheet_name:
            relation_id = sheet.attrib.get(f"{{{DOC_REL_NS}}}id")
            break
    if not relation_id:
        raise ValueError(f"工作簿中不存在工作表：{sheet_name}")
    relations = ElementTree.fromstring(
        archive.read("xl/_rels/workbook.xml.rels")
    )
    for relation in relations.findall(f"{{{PKG_REL_NS}}}Relationship"):
        if relation.attrib.get("Id") == relation_id:
            target = relation.attrib["Target"].replace("\\", "/")
            return target if target.startswith("xl/") else f"xl/{target.lstrip('/')}"
    raise ValueError(f"无法解析工作表关系：{sheet_name}")


def read_xlsx_rows(path: Path, sheet_name: str) -> list[list[str | None]]:
    if path.stat().st_size > MAX_WORKBOOK_BYTES:
        raise ValueError("XLSX 文件超过 50 MB 安全限制")
    with zipfile.ZipFile(path) as archive:
        if sum(item.file_size for item in archive.infolist()) > MAX_UNCOMPRESSED_BYTES:
            raise ValueError("XLSX 解压后超过 200 MB 安全限制")
        shared = _shared_strings(archive)
        sheet = ElementTree.fromstring(archive.read(_sheet_path(archive, sheet_name)))
    rows: list[list[str | None]] = []
    for row in sheet.findall(f".//{{{MAIN_NS}}}sheetData/{{{MAIN_NS}}}row"):
        values: dict[int, str | None] = {}
        for cell in row.findall(f"{{{MAIN_NS}}}c"):
            index = _column_index(cell.attrib.get("r", "A1"))
            cell_type = cell.attrib.get("t")
            value_node = cell.find(f"{{{MAIN_NS}}}v")
            if cell_type == "inlineStr":
                value = "".join(
                    node.text or ""
                    for node in cell.findall(f".//{{{MAIN_NS}}}t")
                )
            elif value_node is None:
                value = None
            elif cell_type == "s":
                value = shared[int(value_node.text or "0")]
            else:
                value = value_node.text
            values[index] = value
        width = max(values, default=-1) + 1
        rows.append([values.get(index) for index in range(width)])
        if len(rows) > MAX_ROWS:
            raise ValueError("工作表超过 100000 行安全限制")
    return rows


def _cell(row: list[str | None], index: int) -> str:
    if index >= len(row) or row[index] is None:
        return ""
    return str(row[index]).strip()


def _company_and_project(label: str) -> tuple[str, str | None]:
    projects = [match.group("project").strip() for match in PROJECT.finditer(label)]
    company = PROJECT.sub("", label).strip(" -—｜|")
    project = " / ".join(dict.fromkeys(projects)) if projects else None
    return company, project


def _role_family(role: str) -> str:
    for family, pattern in ROLE_FAMILIES:
        if pattern.search(role):
            return family
    return "其他/待归类"


def _existing_company_index(
    dictionaries: IdentityDictionaries,
) -> dict[str, dict[str, object]]:
    result: dict[str, dict[str, object]] = {}
    for item in dictionaries.companies:
        for name in [str(item["canonical"]), *item.get("aliases", [])]:
            result[_token(name)] = dict(item)
    return result


def _existing_role_index(
    dictionaries: IdentityDictionaries,
) -> dict[str, dict[str, object]]:
    result: dict[str, dict[str, object]] = {}
    for item in dictionaries.roles:
        for name in [str(item["canonical"]), *item.get("aliases", [])]:
            result[_token(name)] = dict(item)
    return result


def _existing_program_index(
    dictionaries: IdentityDictionaries,
) -> dict[tuple[str, str], dict[str, object]]:
    result: dict[tuple[str, str], dict[str, object]] = {}
    for item in dictionaries.programs:
        company_id = str(item.get("company_id") or "")
        for name in [str(item["canonical"]), *item.get("aliases", [])]:
            result[(company_id, _token(name))] = dict(item)
    return result


def compile_rows(
    rows: Iterable[list[str | None]],
    dictionaries: IdentityDictionaries,
) -> dict[str, object]:
    rows = list(rows)
    header_index = next(
        (
            index
            for index, row in enumerate(rows)
            if "公司及项目名称" in row and "职位名称" in row
        ),
        None,
    )
    if header_index is None:
        raise ValueError("未找到“公司及项目名称/职位名称”表头")
    headers = {str(value): index for index, value in enumerate(rows[header_index]) if value}
    company_column = headers["公司及项目名称"]
    role_column = headers["职位名称"]
    type_column = headers.get("招聘类型")

    existing_companies = _existing_company_index(dictionaries)
    existing_roles = _existing_role_index(dictionaries)
    existing_programs = _existing_program_index(dictionaries)
    companies: dict[str, dict[str, object]] = {}
    programs: dict[str, dict[str, object]] = {}
    roles: dict[str, dict[str, object]] = {}
    skipped_non_roles: set[str] = set()

    for row in rows[header_index + 1 :]:
        label = _cell(row, company_column)
        if not label:
            continue
        company, project = _company_and_project(label)
        if not company:
            continue
        company_token = _token(company)
        existing_company = existing_companies.get(company_token)
        company_id = (
            str(existing_company["id"])
            if existing_company
            else _stable_id("company", company)
        )
        item = companies.setdefault(
            company_id,
            {
                "id": company_id,
                "canonical": (
                    str(existing_company["canonical"])
                    if existing_company
                    else company
                ),
                "aliases": set(existing_company.get("aliases", []))
                if existing_company
                else set(),
                "email_domains": list(existing_company.get("email_domains", []))
                if existing_company
                else [],
                "business_units": list(existing_company.get("business_units", []))
                if existing_company
                else [],
            },
        )
        if label != item["canonical"]:
            item["aliases"].add(label)  # type: ignore[union-attr]

        if project:
            existing_program = existing_programs.get((company_id, _token(project)))
            program_id = (
                str(existing_program["id"])
                if existing_program
                else _stable_id("program", company_id, project)
            )
            recruiting_year = 2027 if type_column is not None and "27" in _cell(row, type_column) else None
            program_item = programs.setdefault(
                program_id,
                {
                    "id": program_id,
                    "company_id": company_id,
                    "canonical": (
                        str(existing_program["canonical"])
                        if existing_program
                        else project
                    ),
                    "aliases": set(existing_program.get("aliases", []))
                    if existing_program
                    else set(),
                    "recruiting_year": (
                        existing_program.get("recruiting_year")
                        if existing_program
                        else recruiting_year
                    ),
                },
            )
            if project != program_item["canonical"]:
                program_item["aliases"].add(project)  # type: ignore[union-attr]

        for raw_role in ROLE_SPLIT.split(_cell(row, role_column)):
            role = raw_role.strip(" -—｜|")
            if not role:
                continue
            if NON_ROLE.search(role):
                skipped_non_roles.add(role)
                continue
            token = _token(role)
            if token in existing_roles:
                continue
            role_id = _stable_id("role", role)
            role_item = roles.setdefault(
                role_id,
                {
                    "id": role_id,
                    "canonical": role,
                    "aliases": set(),
                    "category": _role_family(role),
                },
            )
            if role != role_item["canonical"]:
                role_item["aliases"].add(role)  # type: ignore[union-attr]

    company_values = []
    for item in companies.values():
        item["aliases"] = sorted(item["aliases"])  # type: ignore[arg-type]
        company_values.append(item)
    role_values = []
    for item in roles.values():
        item["aliases"] = sorted(item["aliases"])  # type: ignore[arg-type]
        role_values.append(item)
    program_values = []
    for item in programs.values():
        item["aliases"] = sorted(item["aliases"])  # type: ignore[arg-type]
        program_values.append(item)
    return {
        "companies": sorted(company_values, key=lambda item: str(item["canonical"])),
        "programs": sorted(program_values, key=lambda item: (str(item["company_id"]), str(item["canonical"]))),
        "roles": sorted(role_values, key=lambda item: str(item["canonical"])),
        "skipped_non_roles": sorted(skipped_non_roles),
    }


def compile_workbook(
    source: Path,
    output_directory: Path,
    dictionaries: IdentityDictionaries,
    *,
    sheet_name: str = "2027秋招信息表",
) -> dict[str, object]:
    result = compile_rows(read_xlsx_rows(source, sheet_name), dictionaries)
    output_directory.mkdir(parents=True, exist_ok=True)
    documents = {
        "companies.yml": {"version": 1, "companies": result["companies"]},
        "programs.yml": {"version": 1, "programs": result["programs"]},
        "roles.yml": {"version": 1, "roles": result["roles"]},
    }
    for filename, payload in documents.items():
        _atomic_write(
            output_directory / filename,
            yaml.safe_dump(
                payload,
                allow_unicode=True,
                sort_keys=False,
                default_flow_style=False,
            ),
        )
    report = {
        "compiled_at": datetime.now(timezone.utc).isoformat(),
        "source_filename": source.name,
        "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "sheet_name": sheet_name,
        "counts": {
            "companies": len(result["companies"]),
            "programs": len(result["programs"]),
            "roles": len(result["roles"]),
            "skipped_non_roles": len(result["skipped_non_roles"]),
        },
        "privacy": {
            "links_copied": False,
            "annotations_copied": False,
            "contact_information_copied": False,
        },
    }
    _atomic_write(
        output_directory / "compilation-report.json",
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
    )
    return report
