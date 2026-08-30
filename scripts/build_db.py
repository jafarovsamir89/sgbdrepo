#!/usr/bin/env python3
"""Build a normalized BMW F/G diagnostic database from generated SGBD markdown docs.

The parser is intentionally conservative:
- accepts only UDS 22/2C live data and 2F/31 active tests/routines;
- keeps the original BMW label/description;
- generates human-readable names through config/naming_rules.json;
- marks anything ambiguous for review instead of guessing.

Usage:
  python scripts/build_db.py \
      --source sources/ediabasx-docs-sgbd/docs/sgbd \
      --out data/generated
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Iterable, Optional

ALLOWED_SERVICES = {"22", "2C", "2F", "31"}
HEX_ID_RE = re.compile(r"^0x([0-9A-Fa-f]{4})$")
SERVICE_RE = re.compile(r"^(?:22|2C|2F|31)(?:;(?:22|2C|2F|31))*$", re.I)


@dataclass
class RawFunction:
    source_file: str
    sgbd: str
    source_label: str
    identifier: str
    result_name: Optional[str]
    description: str
    unit: Optional[str]
    data_type: Optional[str]
    multiply: Optional[float]
    divide: Optional[float]
    offset: Optional[float]
    services: list[str]
    arg_table: Optional[str]
    result_table: Optional[str]


def split_md_row(line: str) -> list[str]:
    line = line.strip().strip("|")
    return [c.strip() for c in line.split("|")]


def is_separator(cells: list[str]) -> bool:
    return bool(cells) and all(re.fullmatch(r":?-{3,}:?", c.replace(" ", "")) for c in cells)


def parse_float(value: str) -> Optional[float]:
    value = (value or "").strip()
    if not value or value == "-":
        return None
    try:
        return float(value.replace(",", "."))
    except ValueError:
        return None


def norm_header(text: str) -> str:
    return re.sub(r"[^A-Z0-9]+", "_", text.upper()).strip("_")


def find_col(headers: list[str], *aliases: str) -> Optional[int]:
    h = [norm_header(x) for x in headers]
    aliases = tuple(norm_header(x) for x in aliases)
    for alias in aliases:
        if alias in h:
            return h.index(alias)
    return None


def value(cells: list[str], idx: Optional[int]) -> str:
    if idx is None or idx >= len(cells):
        return ""
    return cells[idx].strip()


def parse_table(headers: list[str], rows: list[list[str]], source_file: Path) -> Iterable[RawFunction]:
    id_idx = find_col(headers, "ID", "IDENTIFIER", "DID", "RID")
    service_idx = find_col(headers, "SERVICE", "SERVICES", "UDS")
    if id_idx is None or service_idx is None:
        return []

    label_idx = find_col(headers, "ARG", "LABEL", "FUNCTION", "FUNKTION")
    result_idx = find_col(headers, "RESULTNAME", "RESULT_NAME")
    info_idx = find_col(headers, "INFO", "DESCRIPTION", "BESCHREIBUNG")
    unit_idx = find_col(headers, "EINHEIT", "UNIT")
    type_idx = find_col(headers, "DATENTYP", "DATA_TYPE", "TYPE")
    mul_idx = find_col(headers, "MUL", "MULTIPLY")
    div_idx = find_col(headers, "DIV", "DIVIDE")
    add_idx = find_col(headers, "ADD", "OFFSET")
    arg_table_idx = find_col(headers, "ARG_TABELLE", "ARG_TABLE")
    res_table_idx = find_col(headers, "RES_TABELLE", "RESULT_TABLE", "RES_TABLE")

    out: list[RawFunction] = []
    for cells in rows:
        ident = value(cells, id_idx)
        m = HEX_ID_RE.fullmatch(ident)
        if not m:
            continue

        service_text = value(cells, service_idx).upper().replace(" ", "")
        if not SERVICE_RE.fullmatch(service_text):
            continue
        services = [s for s in service_text.split(";") if s in ALLOWED_SERVICES]
        if not services:
            continue

        label = value(cells, label_idx) or value(cells, result_idx) or ident
        description = value(cells, info_idx)
        out.append(
            RawFunction(
                source_file=source_file.name,
                sgbd=source_file.stem,
                source_label=label,
                identifier=m.group(1).upper(),
                result_name=value(cells, result_idx) or None,
                description=description,
                unit=(value(cells, unit_idx) or None),
                data_type=(value(cells, type_idx) or None),
                multiply=parse_float(value(cells, mul_idx)),
                divide=parse_float(value(cells, div_idx)),
                offset=parse_float(value(cells, add_idx)),
                services=services,
                arg_table=value(cells, arg_table_idx) or None,
                result_table=value(cells, res_table_idx) or None,
            )
        )
    return out


def parse_markdown(path: Path) -> list[RawFunction]:
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    found: list[RawFunction] = []
    i = 0
    while i + 1 < len(lines):
        if "|" not in lines[i] or "|" not in lines[i + 1]:
            i += 1
            continue
        headers = split_md_row(lines[i])
        sep = split_md_row(lines[i + 1])
        if not is_separator(sep) or len(headers) != len(sep):
            i += 1
            continue
        rows: list[list[str]] = []
        j = i + 2
        while j < len(lines) and "|" in lines[j]:
            row = split_md_row(lines[j])
            if len(row) == len(headers):
                rows.append(row)
            j += 1
        found.extend(parse_table(headers, rows, path))
        i = j
    return found


def load_rules(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def normalize_key(text: str) -> str:
    text = text.upper().strip()
    text = text.replace("Ä", "AE").replace("Ö", "OE").replace("Ü", "UE").replace("ß", "SS")
    text = re.sub(r"\s+", " ", text)
    return text


def humanize_label(label: str) -> str:
    x = label
    for prefix in ("STATUS_", "STAT_", "STEUERN_", "STEUERUNG_"):
        if x.upper().startswith(prefix):
            x = x[len(prefix):]
    x = re.sub(r"^0X[0-9A-F]+_?", "", x, flags=re.I)
    x = re.sub(r"_WERT$", "", x, flags=re.I)
    x = x.replace("_", " ")
    x = re.sub(r"\s+", " ", x).strip()
    return x.title() if x else label


def choose_name(raw: RawFunction, rules: dict) -> tuple[str, str, str, str]:
    candidates = [raw.description, raw.source_label, raw.result_name or ""]
    exact = rules.get("canonical_exact", {})
    for candidate in candidates:
        if not candidate:
            continue
        key = normalize_key(candidate)
        if key in exact:
            r = exact[key]
            return r["canonical_id"], r["name_ru"], r["name_en"], "normalized"

    # Safe fallback: description is human-readable even when not yet translated.
    # We deliberately do not invent a semantic canonical_id.
    base = raw.description.strip(" -") if raw.description else humanize_label(raw.source_label)
    canonical = f"SGBD.{raw.sgbd.upper()}.{raw.identifier}"
    return canonical, base, base, "raw"


def classify(raw: RawFunction) -> str:
    services = set(raw.services)
    if "2F" in services:
        return "activation"
    if "31" in services:
        return "routine"
    return "live_data"


def infer_ecu_family(sgbd: str) -> str:
    s = sgbd.upper()
    for token in (
        "DME", "DDE", "EGS", "DSC", "FEM", "BDC", "IHKA", "ACSM", "EPS", "EMF",
        "SMFA", "SMBF", "HKFM", "NBT", "NBTEVO", "MGU", "ZGW", "REM"
    ):
        if token in s:
            return token
    return "UNKNOWN"


def to_record(raw: RawFunction, rules: dict) -> dict:
    canonical, ru, en, review_status = choose_name(raw, rules)
    primary_service = "2F" if "2F" in raw.services else "31" if "31" in raw.services else "22"
    record = {
        "ecu_family": infer_ecu_family(raw.sgbd),
        "sgbd": raw.sgbd,
        "platforms": [],
        "function_type": classify(raw),
        "canonical_id": canonical,
        "name_ru": ru,
        "name_en": en,
        "source_label": raw.source_label,
        "source_description": raw.description,
        "uds": {
            "service": primary_service,
            "also_supported_services": [s for s in raw.services if s != primary_service],
            "identifier": raw.identifier
        },
        "decode": None,
        "control": None,
        "requirements": {"notes": []},
        "source": {
            "kind": "OEM_PRG_DERIVED",
            "repository": "emdzej/ediabasx-docs-sgbd",
            "path": f"docs/sgbd/{raw.source_file}"
        },
        "confidence": "OEM_PRG",
        "review_status": review_status
    }

    if record["function_type"] == "live_data":
        record["decode"] = {
            "type": raw.data_type,
            "byte_length": None,
            "multiply": raw.multiply,
            "divide": raw.divide,
            "offset": raw.offset,
            "unit": raw.unit,
            "enum_table": raw.result_table
        }
    else:
        record["control"] = {
            "modes": [],
            "arguments": [],
            "safe_default": False,
            "argument_table": raw.arg_table,
            "result_table": raw.result_table
        }
        record["review_status"] = "raw"

    return record


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", type=Path, required=True)
    ap.add_argument("--out", type=Path, default=Path("data/generated"))
    ap.add_argument("--rules", type=Path, default=Path("config/naming_rules.json"))
    args = ap.parse_args()

    rules = load_rules(args.rules)
    args.out.mkdir(parents=True, exist_ok=True)

    total = 0
    by_sgbd: dict[str, list[dict]] = {}
    for md in sorted(args.source.glob("*.md")):
        raws = parse_markdown(md)
        if not raws:
            continue
        records = [to_record(r, rules) for r in raws]
        # Deduplicate exact SGBD/service/identifier/source-label combinations.
        seen = set()
        unique = []
        for r in records:
            key = (r["sgbd"], r["uds"]["service"], r["uds"]["identifier"], r["source_label"])
            if key not in seen:
                seen.add(key)
                unique.append(r)
        by_sgbd[md.stem] = unique
        total += len(unique)

    for sgbd, records in by_sgbd.items():
        (args.out / f"{sgbd}.json").write_text(
            json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    index = {
        "sgbd_count": len(by_sgbd),
        "function_count": total,
        "sgbds": {k: len(v) for k, v in sorted(by_sgbd.items())}
    }
    (args.out / "index.json").write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Generated {total} functions from {len(by_sgbd)} SGBD files")


if __name__ == "__main__":
    main()
