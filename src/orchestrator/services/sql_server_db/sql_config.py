"""Build SQL template variables from db.yml for $(name) substitution in .sql files."""

from typing import TYPE_CHECKING, Dict

from .config import DEFAULT_DATABASE_TYPE, SOURCE_DATABASE_TYPE
from .schema import get_schema_from_config

if TYPE_CHECKING:
    from .factory import DBConnectionFactory


def build_sql_substitution_vars(
    factory: "DBConnectionFactory",
    database_type: str = DEFAULT_DATABASE_TYPE,
) -> Dict[str, str]:
    """
    Return $(variable) replacements derived from db.yml.

    Common placeholders in SQL files:
      [$(prod_schema)].[snp_*]                         — prod objects (procs, snapshots, ctl)
      [$(source_database)].[$(source_schema)].[Dim*]   — cross-DB dimension reads
      [$(source_database)].[dbo].[Fact*]               — cross-DB fact reads
      [$(schema)] / [$(database)]                        — connection executing the script
    """
    source_cfg = factory.get_database_config(SOURCE_DATABASE_TYPE)
    prod_cfg = factory.get_database_config(DEFAULT_DATABASE_TYPE)
    target_cfg = factory.get_database_config(database_type)

    source_schema = get_schema_from_config(source_cfg)
    prod_schema = get_schema_from_config(prod_cfg)
    target_schema = get_schema_from_config(target_cfg)

    return {
        "source_database": source_cfg["database"],
        "source_schema": source_schema,
        "prod_database": prod_cfg["database"],
        "prod_schema": prod_schema,
        "database": target_cfg["database"],
        "schema": target_schema,
    }
