from __future__ import annotations

import io
import re
from typing import Any, Dict, List, Tuple

import pandas as pd


DATE_KEYWORDS = ["日期", "时间", "月份", "年月", "date", "time", "month"]


def _clean_column_name(name: Any) -> str:
    text = str(name).replace("\n", " ").replace("\r", " ").strip()
    text = re.sub(r"\s+", " ", text)
    return text


def load_uploaded_table(uploaded_file) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    file_name = uploaded_file.name
    suffix = file_name.lower().split(".")[-1]
    content = uploaded_file.getvalue()

    if suffix == "csv":
        df = pd.read_csv(io.BytesIO(content))
        meta = {"sheet_name": None}
    elif suffix in {"xlsx", "xls"}:
        excel = pd.ExcelFile(io.BytesIO(content))
        sheet_name = excel.sheet_names[0]
        df = pd.read_excel(excel, sheet_name=sheet_name)
        meta = {"sheet_name": sheet_name}
    else:
        raise ValueError("仅支持 xlsx/xls/csv 文件")

    df.columns = [_clean_column_name(c) for c in df.columns]
    df = df.dropna(axis=1, how="all")
    df = df.dropna(axis=0, how="all")
    df = df.reset_index(drop=True)
    return df, meta


def _infer_column_type(series: pd.Series, col_name: str) -> str:
    non_null = series.dropna()
    if non_null.empty:
        return "empty"

    text_non_null = non_null.astype(str).str.strip()

    # numeric
    numeric_series = pd.to_numeric(
        text_non_null.str.replace(",", "", regex=False).str.replace("%", "", regex=False),
        errors="coerce",
    )
    numeric_ratio = numeric_series.notna().mean()
    if numeric_ratio >= 0.8:
        return "numeric"

    # date
    lowered_col = col_name.lower()
    hint = any(k in col_name for k in DATE_KEYWORDS) or any(k in lowered_col for k in DATE_KEYWORDS)
    date_series = pd.to_datetime(text_non_null, errors="coerce")
    date_ratio = date_series.notna().mean()
    if date_ratio >= 0.8 or (hint and date_ratio >= 0.5):
        return "date"

    nunique = text_non_null.nunique(dropna=True)
    unique_ratio = nunique / max(len(text_non_null), 1)
    if nunique <= 50 or unique_ratio <= 0.3:
        return "categorical"

    return "text"


def build_dataframe_profile(df: pd.DataFrame) -> Dict[str, Any]:
    numeric_fields: List[str] = []
    date_fields: List[str] = []
    categorical_fields: List[str] = []
    text_fields: List[str] = []
    columns: List[Dict[str, Any]] = []

    for col in df.columns:
        col_type = _infer_column_type(df[col], col)
        sample_values = df[col].dropna().astype(str).head(5).tolist()
        info = {
            "name": col,
            "type": col_type,
            "sample_values": sample_values,
            "non_null_count": int(df[col].notna().sum()),
            "unique_count": int(df[col].nunique(dropna=True)),
        }
        columns.append(info)

        if col_type == "numeric":
            numeric_fields.append(col)
        elif col_type == "date":
            date_fields.append(col)
        elif col_type == "categorical":
            categorical_fields.append(col)
        elif col_type == "text":
            text_fields.append(col)

    return {
        "row_count": int(len(df)),
        "column_count": int(len(df.columns)),
        "columns": columns,
        "numeric_fields": numeric_fields,
        "date_fields": date_fields,
        "categorical_fields": categorical_fields,
        "text_fields": text_fields,
        "all_fields": list(df.columns),
    }
