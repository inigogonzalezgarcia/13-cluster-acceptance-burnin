"""Acceptance criteria, read from a TOML file. Unknown keys are errors: a typo must not silently
relax a criterion the customer signed."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

SCHEMA = {
    "cluster": {"name": str, "min_accepted_gpu_fraction": float},
    "inventory": {"gpus_per_node": int, "gpu_model": str, "driver_version": str, "vbios_version": str,
                  "ib_ports_per_node": int, "ib_rate_gbps": int, "max_ib_symbol_errors": int},
    "diag": {"level": int, "required_tests": list, "warn_counts_as_pass": bool},
    "nccl": {"node": {"min_busbw_gbps": float}, "rack": {"min_busbw_gbps": float, "min_nodes": int}},
    "burnin": {"hours": int, "max_gpu_temp_c": float, "max_throttle_fraction": float, "max_dbe": int,
               "sbe_warn_per_gpu": int, "max_sbe_per_gpu": int, "hardware_xids": list,
               "min_workload_pass_rate": float, "job": {"min_mtbi_hours": float, "min_goodput": float}},
}


@dataclass
class Criteria:
    raw: dict

    def __getitem__(self, section: str) -> dict:
        return self.raw[section]


def load(path: str | Path) -> Criteria:
    with open(path, "rb") as f:
        try:
            raw = tomllib.load(f)
        except tomllib.TOMLDecodeError as e:
            raise ValueError(f"{path}: {e}") from None
    errs: list[str] = []
    _check(raw, SCHEMA, "", errs)
    c = raw.get("cluster", {})
    if not 0 < c.get("min_accepted_gpu_fraction", 0) <= 1:
        errs.append("cluster.min_accepted_gpu_fraction must be in (0, 1]")
    if errs:
        raise ValueError(f"{path}: " + "; ".join(errs))
    return Criteria(raw)


def _check(raw: dict, schema: dict, prefix: str, errs: list[str]) -> None:
    for key in raw:
        if key not in schema:
            errs.append(f"unknown key {prefix}{key}")
    for key, typ in schema.items():
        if key not in raw:
            errs.append(f"missing {prefix}{key}")
        elif isinstance(typ, dict):
            if not isinstance(raw[key], dict):
                errs.append(f"{prefix}{key} must be a table")
            else:
                _check(raw[key], typ, f"{prefix}{key}.", errs)
        elif typ is float:
            if not isinstance(raw[key], (int, float)) or isinstance(raw[key], bool):
                errs.append(f"{prefix}{key} must be a number")
        elif not isinstance(raw[key], typ) or (typ is int and isinstance(raw[key], bool)):
            errs.append(f"{prefix}{key} must be {typ.__name__}")
