"""
[INPUT]
pydantic::BaseModel, Field
enum::Enum
typing::List, Dict, Optional, Union

[OUTPUT]
- SpreadsheetTheme: Four publication-grade business theme palettes
- ColumnType: Column data type inference enum
- SpreadsheetColumn: Column definition model
- SpreadsheetRow: Row record cell mapping model
- SpreadsheetGenerateRequest: Payload to generate styled Excel spreadsheet
- OfficePlatform: Target office ecosystem platform enum
- OfficeSyncRequest: Payload to sync table records to office suite
- OfficeSyncResponse: Result response payload of office sync

[POS]
Pydantic contracts for HighAestheticStyledSpreadsheetGeneratorAndMultiOfficeSyncPipeline.
Single file < 120 lines. Zero `Any` types.
"""

from enum import Enum
from typing import Dict, List, Optional, Union

from pydantic import BaseModel, Field


class SpreadsheetTheme(str, Enum):
    BUSINESS_NAVY = "business_navy"
    DARK_GOLD = "dark_gold"
    FINANCIAL_EMERALD = "financial_emerald"
    TECH_SLATE = "tech_slate"


class ColumnType(str, Enum):
    STRING = "string"
    NUMBER = "number"
    CURRENCY = "currency"
    PERCENTAGE = "percentage"
    DATE = "date"


class SpreadsheetColumn(BaseModel):
    key: str = Field(..., description="Unique field identifier")
    label: str = Field(..., description="Human-readable column header")
    col_type: ColumnType = Field(default=ColumnType.STRING, description="Column data type")
    width: Optional[int] = Field(default=None, description="Custom column width override")


class SpreadsheetRow(BaseModel):
    cells: Dict[str, Union[str, int, float, bool, None]] = Field(
        default_factory=dict,
        description="Key-value mapping of cell data matching column keys",
    )


class SpreadsheetGenerateRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=120, description="Title of the spreadsheet report")
    theme: SpreadsheetTheme = Field(
        default=SpreadsheetTheme.BUSINESS_NAVY,
        description="Selected publication theme palette",
    )
    columns: List[SpreadsheetColumn] = Field(..., min_length=1, description="List of columns")
    rows: List[SpreadsheetRow] = Field(default_factory=list, description="List of rows")
    sheet_name: str = Field(default="Sheet1", max_length=31, description="Worksheet tab name")


class OfficePlatform(str, Enum):
    FEISHU_BITABLE = "feishu_bitable"
    WECOM_DOC = "wecom_doc"
    DINGTALK_TABLE = "dingtalk_table"


class OfficeSyncRequest(BaseModel):
    platform: OfficePlatform = Field(..., description="Target office platform")
    table_name: str = Field(..., min_length=1, max_length=120, description="Table name in target suite")
    columns: List[SpreadsheetColumn] = Field(..., min_length=1, description="Table column definitions")
    rows: List[SpreadsheetRow] = Field(default_factory=list, description="Table row records to insert")


class OfficeSyncResponse(BaseModel):
    platform: OfficePlatform
    success: bool
    sync_id: str
    url: str
    record_count: int
    message: str
