from __future__ import annotations

from dataclasses import dataclass
from functools import cached_property
from importlib.resources import files
from pathlib import Path
import re
from typing import Any
import unicodedata

import yaml


DICTIONARY_FILES = (
    "companies.yml",
    "programs.yml",
    "roles.yml",
    "mail_templates.yml",
)

ROOT_KEYS = {
    "companies.yml": {"version", "companies"},
    "programs.yml": {"version", "programs"},
    "roles.yml": {"version", "roles"},
    "mail_templates.yml": {"version", "mail_templates"},
}
COLLECTION_KEYS = {
    "companies.yml": "companies",
    "programs.yml": "programs",
    "roles.yml": "roles",
    "mail_templates.yml": "mail_templates",
}
ITEM_KEYS = {
    "companies.yml": {
        "id",
        "canonical",
        "aliases",
        "email_domains",
        "business_units",
    },
    "programs.yml": {
        "id",
        "company_id",
        "canonical",
        "aliases",
        "recruiting_year",
    },
    "roles.yml": {"id", "canonical", "aliases", "category"},
    "mail_templates.yml": {
        "id",
        "company_id",
        "kind",
        "subject_patterns",
        "body_patterns",
        "identity_fields",
        "creates_application",
    },
}


class DictionaryValidationError(ValueError):
    pass


@dataclass(frozen=True)
class IdentityDictionaries:
    companies: tuple[dict[str, Any], ...]
    programs: tuple[dict[str, Any], ...]
    roles: tuple[dict[str, Any], ...]
    mail_templates: tuple[dict[str, Any], ...]
    sources: tuple[str, ...]

    def counts(self) -> dict[str, int]:
        return {
            "companies": len(self.companies),
            "programs": len(self.programs),
            "roles": len(self.roles),
            "mail_templates": len(self.mail_templates),
        }

    @staticmethod
    def _lookup(value: str) -> str:
        normalized = unicodedata.normalize("NFKC", value)
        return "".join(normalized.casefold().split())

    @cached_property
    def _company_index(self) -> dict[str, str]:
        return {
            self._lookup(name): str(item["id"])
            for item in self.companies
            for name in (str(item["canonical"]), *item.get("aliases", []))
        }

    @cached_property
    def _program_index(self) -> dict[tuple[str | None, str], str]:
        return {
            (item.get("company_id"), self._lookup(name)): str(item["id"])
            for item in self.programs
            for name in (str(item["canonical"]), *item.get("aliases", []))
        }

    @cached_property
    def _role_index(self) -> dict[str, str]:
        return {
            self._lookup(name): str(item["id"])
            for item in self.roles
            for name in (str(item["canonical"]), *item.get("aliases", []))
        }

    def company_id(self, value: str | None) -> str | None:
        if not value:
            return None
        return self._company_index.get(self._lookup(value))

    def program_id(self, company_id: str | None, value: str | None) -> str | None:
        if not value:
            return None
        needle = self._lookup(value)
        if company_id:
            return self._program_index.get((company_id, needle))
        matches = {
            item_id
            for (indexed_company, indexed_name), item_id in self._program_index.items()
            if indexed_name == needle
        }
        return next(iter(matches)) if len(matches) == 1 else None

    def role_id(self, value: str | None) -> str | None:
        if not value:
            return None
        return self._role_index.get(self._lookup(value))

    def mail_template_for(
        self,
        *,
        company: str | None,
        title: str,
        content: str = "",
    ) -> dict[str, Any] | None:
        """Match a reviewed mail template without retaining the source body."""
        company_id = self.company_id(company)
        for item in self.mail_templates:
            template_company = item.get("company_id")
            if template_company and template_company != company_id:
                continue
            subject_patterns = item.get("subject_patterns", [])
            body_patterns = item.get("body_patterns", [])
            subject_matches = not subject_patterns or any(
                re.search(pattern, title, re.IGNORECASE)
                for pattern in subject_patterns
            )
            body_matches = not body_patterns or any(
                re.search(pattern, content, re.IGNORECASE)
                for pattern in body_patterns
            )
            if subject_matches and body_matches:
                return item
        return None


def _read_yaml(path: Path) -> dict[str, Any]:
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise DictionaryValidationError(f"无法读取词典 {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise DictionaryValidationError(f"词典根节点必须是映射: {path}")
    return payload


def _validate_document(name: str, payload: dict[str, Any], source: str) -> list[dict[str, Any]]:
    unknown_root = set(payload) - ROOT_KEYS[name]
    if unknown_root:
        raise DictionaryValidationError(
            f"{source} 包含未知根字段: {', '.join(sorted(unknown_root))}"
        )
    if payload.get("version") != 1:
        raise DictionaryValidationError(f"{source} 的 version 必须为 1")
    collection_name = COLLECTION_KEYS[name]
    collection = payload.get(collection_name)
    if not isinstance(collection, list):
        raise DictionaryValidationError(f"{source}.{collection_name} 必须是列表")
    validated: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for index, raw_item in enumerate(collection):
        location = f"{source}.{collection_name}[{index}]"
        if not isinstance(raw_item, dict):
            raise DictionaryValidationError(f"{location} 必须是映射")
        unknown = set(raw_item) - ITEM_KEYS[name]
        if unknown:
            raise DictionaryValidationError(
                f"{location} 包含未知字段: {', '.join(sorted(unknown))}"
            )
        item = dict(raw_item)
        item_id = item.get("id")
        if not isinstance(item_id, str) or not item_id.strip():
            raise DictionaryValidationError(f"{location}.id 必须是非空字符串")
        if item_id in seen_ids:
            raise DictionaryValidationError(f"{source} 存在重复 id: {item_id}")
        seen_ids.add(item_id)
        if name != "mail_templates.yml":
            canonical = item.get("canonical")
            if not isinstance(canonical, str) or not canonical.strip():
                raise DictionaryValidationError(
                    f"{location}.canonical 必须是非空字符串"
                )
        if "company_id" in item and item["company_id"] is not None and not isinstance(
            item["company_id"], str
        ):
            raise DictionaryValidationError(
                f"{location}.company_id 必须是字符串或 null"
            )
        if "recruiting_year" in item and item["recruiting_year"] is not None:
            year = item["recruiting_year"]
            if not isinstance(year, int) or not 2000 <= year <= 2100:
                raise DictionaryValidationError(
                    f"{location}.recruiting_year 必须是 2000–2100 的整数或 null"
                )
        if name == "mail_templates.yml":
            if not isinstance(item.get("kind"), str) or not item["kind"].strip():
                raise DictionaryValidationError(
                    f"{location}.kind 必须是非空字符串"
                )
            if not isinstance(item.get("creates_application"), bool):
                raise DictionaryValidationError(
                    f"{location}.creates_application 必须是布尔值"
                )
        for list_key in (
            "aliases",
            "email_domains",
            "business_units",
            "subject_patterns",
            "body_patterns",
            "identity_fields",
        ):
            if list_key not in item:
                continue
            value = item[list_key]
            if not isinstance(value, list) or not all(
                isinstance(entry, str) and entry.strip() for entry in value
            ):
                raise DictionaryValidationError(
                    f"{location}.{list_key} 必须是非空字符串列表"
                )
        validated.append(item)
    return validated


def _built_in_path(name: str) -> Path:
    resource = files("job_mail_desk").joinpath("identity_data", name)
    return Path(str(resource))


def _merge_by_id(
    built_in: list[dict[str, Any]],
    override: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    merged = {str(item["id"]): item for item in built_in}
    for item in override:
        merged[str(item["id"])] = item
    return list(merged.values())


def _validate_references(documents: dict[str, list[dict[str, Any]]]) -> None:
    company_ids = {str(item["id"]) for item in documents["companies.yml"]}
    for name in ("programs.yml", "mail_templates.yml"):
        for item in documents[name]:
            company_id = item.get("company_id")
            if company_id and company_id not in company_ids:
                raise DictionaryValidationError(
                    f"{name} 中的 {item['id']} 引用了未知公司 {company_id}"
                )

    aliases: dict[tuple[str, str], str] = {}
    for name in ("companies.yml", "programs.yml", "roles.yml"):
        for item in documents[name]:
            namespace = str(item.get("company_id") or name)
            values = [str(item["canonical"]), *item.get("aliases", [])]
            for value in values:
                normalized = IdentityDictionaries._lookup(value)
                key = (namespace, normalized)
                previous = aliases.get(key)
                if previous and previous != item["id"]:
                    raise DictionaryValidationError(
                        f"{name} 别名冲突: {value} 同时属于 {previous} 与 {item['id']}"
                    )
                aliases[key] = str(item["id"])


def load_identity_dictionaries(
    user_directory: Path | None = None,
) -> IdentityDictionaries:
    documents: dict[str, list[dict[str, Any]]] = {}
    sources: list[str] = []
    for name in DICTIONARY_FILES:
        built_in_path = _built_in_path(name)
        built_in = _validate_document(name, _read_yaml(built_in_path), str(built_in_path))
        sources.append(str(built_in_path))
        merged = built_in
        if user_directory:
            layers = (
                user_directory / "imported",
                user_directory,
                user_directory / "manual",
            )
            for layer in layers:
                override_path = layer / name
                if not override_path.exists():
                    continue
                override = _validate_document(
                    name,
                    _read_yaml(override_path),
                    str(override_path),
                )
                sources.append(str(override_path))
                merged = _merge_by_id(merged, override)
        documents[name] = merged
    _validate_references(documents)
    return IdentityDictionaries(
        companies=tuple(documents["companies.yml"]),
        programs=tuple(documents["programs.yml"]),
        roles=tuple(documents["roles.yml"]),
        mail_templates=tuple(documents["mail_templates.yml"]),
        sources=tuple(sources),
    )
