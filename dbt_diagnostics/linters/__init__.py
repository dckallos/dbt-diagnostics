from .base import BaseLinter
from .contract_column_count import ContractColumnCountLinter
from .type_hazard import TypeHazardLinter
from .duplicate_alias import DuplicateAliasLinter
from .missing_contract_column import MissingContractColumnLinter

# Registry: all linters to run during `dbt-diagnostics lint`
LINTER_REGISTRY: list[type[BaseLinter]] = [
    ContractColumnCountLinter,
    TypeHazardLinter,
    DuplicateAliasLinter,
    MissingContractColumnLinter,
]

__all__ = [
    'BaseLinter',
    'ContractColumnCountLinter',
    'TypeHazardLinter',
    'DuplicateAliasLinter',
    'MissingContractColumnLinter',
    'LINTER_REGISTRY',
]
