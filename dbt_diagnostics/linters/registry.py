"""
dbt_diagnostics/linters/registry.py

Linter registry and dispatch logic.
"""

from dbt_diagnostics.linters.base import BaseLinter
from dbt_diagnostics.linters.contract_column_count import ContractColumnCountLinter
from dbt_diagnostics.linters.type_hazard import TypeHazardLinter
from dbt_diagnostics.linters.duplicate_alias import DuplicateAliasLinter
from dbt_diagnostics.linters.missing_contract_column import MissingContractColumnLinter

# Order matters for reporting consistency.
LINTER_REGISTRY: list[type[BaseLinter]] = [
    ContractColumnCountLinter,
    TypeHazardLinter,
    DuplicateAliasLinter,
    MissingContractColumnLinter,
]
