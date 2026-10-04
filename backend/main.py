from fastapi import FastAPI, UploadFile, File, HTTPException, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from jose import JWTError, jwt
from passlib.context import CryptContext
from datetime import datetime, timedelta
from pymongo import MongoClient
from dotenv import load_dotenv
from collections import Counter

import os
import re
import tempfile
import numpy as np
import pandas as pd
from reportlab.lib.pagesizes import A4
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    KeepTogether,
)
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
load_dotenv()

app = FastAPI(
    title="AI Business Analyst API",
    description="Backend API for the AI Business Analyst platform",
    version="1.0.0"
)
# =========================
# Authentication Setup
# =========================

SECRET_KEY = os.getenv("SECRET_KEY")

if not SECRET_KEY:
    raise RuntimeError(
        "SECRET_KEY is missing from .env file."
    )

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60

pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto"
)

# MongoDB Connection
MONGO_URL = "mongodb://localhost:27017"

client = MongoClient(MONGO_URL)

db = client["ai_business_analyst"]

users_db = db["users"]

def hash_password(password: str):
    return pwd_context.hash(password)


def verify_password(password: str, hashed_password: str):
    return pwd_context.verify(password, hashed_password)


def create_access_token(data: dict):
    to_encode = data.copy()

    expire = datetime.utcnow() + timedelta(
        minutes=ACCESS_TOKEN_EXPIRE_MINUTES
    )

    to_encode.update({
        "exp": expire
    })

    return jwt.encode(
        to_encode,
        SECRET_KEY,
        algorithm=ALGORITHM
    )

# =========================
# User-Specific Datasets
# =========================

user_datasets = {}

# Maximum allowed uploaded dataset size: 100 MB = 100 * 1024 * 1024 bytes.
MAX_UPLOAD_SIZE_BYTES = 100 * 1024 * 1024


class ForecastRequest(BaseModel):
    column: str
    periods: int = Field(default=5, ge=1, le=120)


class RegisterRequest(BaseModel):
    name: str
    email: str
    password: str


class LoginRequest(BaseModel):
    email: str
    password: str


class AIAnalysisQuestion(BaseModel):
    question: str = Field(min_length=1, max_length=2000)


class DataCleaningApplyRequest(BaseModel):
    actions: list[str] = Field(default_factory=list)


class WhatIfRequest(BaseModel):
    column: str = Field(min_length=1, max_length=200)
    scenario_type: str = Field(default="increase_by_percent")
    change_percent: float | None = Field(default=None, ge=-100, le=1000000)
    change_value: float | None = Field(default=None, ge=-1_000_000_000_000, le=1_000_000_000_000)


def _safe_ratio(numerator, denominator):
    if denominator in (None, 0):
        return 0
    return round((numerator / denominator) * 100, 2)


def _detect_date_columns(df):
    date_columns = []

    for column in df.columns:
        series = df[column].dropna()
        if series.empty:
            continue

        try:
            parsed = pd.to_datetime(series, errors="coerce")
            valid_ratio = parsed.notna().sum() / len(series)
            if valid_ratio >= 0.8:
                date_columns.append(str(column))
        except Exception:
            continue

    return date_columns


def _calculate_data_quality_score(df):
    if df is None or df.empty:
        return 0

    rows, columns = df.shape
    total_cells = rows * columns
    if total_cells == 0:
        return 0

    missing_cells = int(df.isna().sum().sum())
    duplicate_rows = int(df.duplicated().sum())
    penalty_weight = missing_cells + (duplicate_rows * 2)
    score = 100 - ((penalty_weight / total_cells) * 100)
    return round(max(0, min(100, score)), 2)


def _analyze_numeric_outliers(series):
    if len(series) < 4:
        return 0

    numeric_series = pd.to_numeric(series, errors="coerce").dropna()
    if numeric_series.empty:
        return 0

    q1 = numeric_series.quantile(0.25)
    q3 = numeric_series.quantile(0.75)
    iqr = q3 - q1
    if pd.isna(iqr) or iqr == 0:
        return 0

    lower_bound = q1 - 1.5 * iqr
    upper_bound = q3 + 1.5 * iqr
    return int(((numeric_series < lower_bound) | (numeric_series > upper_bound)).sum())


def _build_cleaning_plan(df):
    if df is None or df.empty:
        return {
            "summary": {"rows": 0, "columns": 0, "data_quality_score": 0, "issues_found": 0},
            "issues": [],
            "recommendations": [],
            "cleaning_actions": [],
        }

    rows, columns = df.shape
    issues = []
    recommendations = []

    def add_issue(issue_type, column=None, count=0, percentage=0.0, severity="medium",
                  description="", suggested_action=""):
        if not description:
            description = "Detected during data quality review."
        if not suggested_action:
            suggested_action = "Review this issue before finalizing the dataset."
        issues.append({
            "type": issue_type,
            "column": column,
            "count": int(count),
            "percentage": round(float(percentage), 2),
            "severity": severity,
            "description": description,
            "suggested_action": suggested_action,
        })

    for column in df.columns:
        missing_count = int(df[column].isna().sum())
        if missing_count > 0:
            percentage = (missing_count / rows) * 100 if rows else 0
            severity = "critical" if percentage >= 25 else "high" if percentage >= 10 else "medium" if percentage >= 3 else "low"
            action = "Fill missing numeric values with median." if pd.api.types.is_numeric_dtype(df[column]) else "Fill missing categorical values with mode or Unknown."
            add_issue(
                "missing_values",
                column=str(column),
                count=missing_count,
                percentage=percentage,
                severity=severity,
                description=f"Missing values detected in {column}.",
                suggested_action=action,
            )

        if df[column].dtype == object:
            text_series = df[column].astype(str)
            whitespace_count = int(text_series.str.strip().ne(text_series).sum())
            if whitespace_count > 0:
                add_issue(
                    "whitespace",
                    column=str(column),
                    count=whitespace_count,
                    percentage=(whitespace_count / rows) * 100 if rows else 0,
                    severity="medium",
                    description="Leading or trailing spaces were detected in text values.",
                    suggested_action="Trim leading and trailing spaces.",
                )

            empty_string_count = int(text_series.str.strip().eq("").sum())
            if empty_string_count > 0:
                add_issue(
                    "empty_strings",
                    column=str(column),
                    count=empty_string_count,
                    percentage=(empty_string_count / rows) * 100 if rows else 0,
                    severity="medium",
                    description="Empty string values were found in the column.",
                    suggested_action="Replace empty values with null or a default category.",
                )

            normalized = text_series.str.strip().str.lower()
            unique_original = text_series.dropna().nunique()
            unique_normalized = normalized.dropna().nunique()
            if unique_original > 1 and unique_normalized < unique_original:
                add_issue(
                    "categorical_inconsistency",
                    column=str(column),
                    count=int(unique_original - unique_normalized),
                    percentage=((unique_original - unique_normalized) / max(unique_original, 1)) * 100,
                    severity="medium",
                    description="Values appear inconsistent due to capitalization or formatting differences.",
                    suggested_action="Normalize category names to a consistent format.",
                )

            if rows > 20 and unique_original > max(15, rows * 0.5):
                add_issue(
                    "high_cardinality",
                    column=str(column),
                    count=int(unique_original),
                    percentage=(unique_original / rows) * 100,
                    severity="low",
                    description="This column has very high cardinality and may be difficult to segment effectively.",
                    suggested_action="Review whether this column is useful as a categorical dimension.",
                )

    duplicate_rows = int(df.duplicated().sum())
    if duplicate_rows > 0:
        add_issue(
            "duplicate_rows",
            column=None,
            count=duplicate_rows,
            percentage=(duplicate_rows / rows) * 100 if rows else 0,
            severity="high" if duplicate_rows > 0 else "low",
            description="Duplicate rows were detected in the dataset.",
            suggested_action="Remove duplicate rows before analysis or reporting.",
        )

    duplicate_column_names = [name for name, count in Counter(df.columns).items() if count > 1]
    if duplicate_column_names:
        add_issue(
            "duplicate_columns",
            column=duplicate_column_names[0],
            count=len(duplicate_column_names),
            percentage=(len(duplicate_column_names) / max(len(df.columns), 1)) * 100,
            severity="medium",
            description="The dataset contains duplicate column names that may confuse downstream analysis.",
            suggested_action="Rename or merge duplicate columns before proceeding.",
        )

    for column in df.select_dtypes(include=[np.number]).columns:
        numeric_series = pd.to_numeric(df[column], errors="coerce")
        invalid_numeric_count = int((df[column].notna() & numeric_series.isna()).sum())
        if invalid_numeric_count > 0:
            add_issue(
                "invalid_numeric_values",
                column=str(column),
                count=invalid_numeric_count,
                percentage=(invalid_numeric_count / rows) * 100 if rows else 0,
                severity="high",
                description="The column contains values that are not valid numeric entries.",
                suggested_action="Convert invalid values to NaN and then clean or fill them.",
            )

        inf_count = int(np.isinf(numeric_series.to_numpy(dtype=float, na_value=np.nan)).sum())
        if inf_count > 0:
            add_issue(
                "infinite_values",
                column=str(column),
                count=inf_count,
                percentage=(inf_count / rows) * 100 if rows else 0,
                severity="high",
                description="Infinite values were detected in a numeric column.",
                suggested_action="Replace infinite values with NaN and handle them before analysis.",
            )

        if rows > 10:
            outlier_count = _analyze_numeric_outliers(df[column])
            if outlier_count > 0:
                add_issue(
                    "outliers",
                    column=str(column),
                    count=outlier_count,
                    percentage=(outlier_count / rows) * 100 if rows else 0,
                    severity="medium" if outlier_count <= 5 else "high",
                    description="Extreme values were detected and may distort summary metrics.",
                    suggested_action="Review extreme values before removing or adjusting them.",
                )

        if numeric_series.nunique(dropna=True) <= 1 and numeric_series.notna().sum() > 0:
            add_issue(
                "constant_column",
                column=str(column),
                count=int(numeric_series.notna().sum()),
                percentage=100,
                severity="low",
                description="The numeric column has almost no variation and may not add much analytical value.",
                suggested_action="Consider removing the column after business review.",
            )

    for column in df.columns:
        series = df[column].dropna()
        if series.empty:
            continue
        if any(keyword in str(column).lower() for keyword in ["date", "time", "month", "year", "day"]):
            parsed = pd.to_datetime(series, errors="coerce")
            if parsed.notna().sum() > 0 and parsed.notna().mean() < 1:
                add_issue(
                    "suspicious_date_column",
                    column=str(column),
                    count=int(series.size - parsed.notna().sum()),
                    percentage=((series.size - parsed.notna().sum()) / series.size) * 100,
                    severity="medium",
                    description="This column appears date-like but contains values that may be invalid or inconsistent.",
                    suggested_action="Review and standardize the date format before using it for time-based analysis.",
                )

    for column in df.columns:
        missing_count = int(df[column].isna().sum())
        if rows > 0 and (missing_count / rows) >= 0.35:
            add_issue(
                "high_missing_percentage",
                column=str(column),
                count=missing_count,
                percentage=(missing_count / rows) * 100,
                severity="high",
                description="A large share of values is missing in this column.",
                suggested_action="Consider removing the column after business review or replacing it with a trusted default.",
            )

    unique_recommendations = []
    for issue in issues:
        action_text = issue.get("suggested_action")
        if action_text and action_text not in unique_recommendations:
            unique_recommendations.append(action_text)

    recommendations.extend(unique_recommendations[:8])

    cleaning_actions = [
        {
            "name": "remove_duplicates",
            "label": "Remove duplicate rows",
            "description": "Delete exact duplicate records before analysis.",
        },
        {
            "name": "trim_text",
            "label": "Trim text spaces",
            "description": "Remove leading and trailing spaces from text values.",
        },
        {
            "name": "fill_numeric_missing",
            "label": "Fill missing numeric values",
            "description": "Impute missing numeric values with the median for each column.",
        },
        {
            "name": "fill_categorical_missing",
            "label": "Fill missing categorical values",
            "description": "Replace missing category values with the mode or Unknown.",
        },
        {
            "name": "replace_infinite",
            "label": "Replace infinite values",
            "description": "Convert infinite values to NaN and clean them.",
        },
        {
            "name": "normalize_categories",
            "label": "Normalize category names",
            "description": "Standardize capitalization and whitespace in categorical values.",
        },
    ]

    summary = {
        "rows": int(rows),
        "columns": int(columns),
        "data_quality_score": _calculate_data_quality_score(df),
        "issues_found": len(issues),
    }

    return {
        "summary": summary,
        "issues": issues,
        "recommendations": recommendations,
        "cleaning_actions": cleaning_actions,
    }


def _json_safe(value):
    if value is None:
        return None

    if isinstance(value, (pd.Timestamp, datetime)):
        return value.isoformat()

    if isinstance(value, dict):
        return {str(key): _json_safe(val) for key, val in value.items()}

    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]

    if isinstance(value, np.ndarray):
        return [_json_safe(item) for item in value.tolist()]

    if isinstance(value, pd.Series):
        return [_json_safe(item) for item in value.tolist()]

    if isinstance(value, (np.integer,)):
        return int(value)

    if isinstance(value, (np.floating, float)):
        if not np.isfinite(value):
            return None
        return float(value)

    if isinstance(value, (np.bool_, bool)):
        return bool(value)

    if pd.isna(value):
        return None

    return value


def _normalize_column_name(column_name):
    return re.sub(r"[^a-z0-9]+", " ", str(column_name).lower()).strip()


def _format_neutral_number(value):
    if value is None:
        return "N/A"

    numeric_value = float(value)
    abs_value = abs(numeric_value)

    if abs_value >= 1_000_000_000:
        return f"{numeric_value / 1_000_000_000:.2f}B"
    if abs_value >= 1_000_000:
        return f"{numeric_value / 1_000_000:.2f}M"
    if abs_value >= 1_000:
        return f"{numeric_value / 1_000:.2f}K"
    if abs_value >= 1:
        return f"{numeric_value:,.2f}"
    if abs_value == 0:
        return "0"
    return f"{numeric_value:,.3f}".rstrip("0").rstrip(".")


def _select_metric_column(df, numeric_columns):
    if not numeric_columns:
        return None

    metric_candidates = []
    for column in numeric_columns:
        series = pd.to_numeric(df[column], errors="coerce").dropna()
        if series.empty:
            continue
        metric_candidates.append({
            "column": str(column),
            "total": float(series.sum()),
            "average": float(series.mean()),
            "max": float(series.max()),
            "std": float(series.std()) if len(series) > 1 else 0.0,
        })

    if not metric_candidates:
        return None

    metric_candidates.sort(key=lambda item: (abs(item["total"]), abs(item["average"]), item["std"]), reverse=True)
    return metric_candidates[0]["column"]


def _build_auto_dashboard_payload(df):
    if df is None or df.empty:
        return {
            "status": "success",
            "dataset": {
                "rows": 0,
                "columns": 0,
                "numeric_columns": [],
                "categorical_columns": [],
                "date_columns": []
            },
            "kpis": [],
            "charts": [],
            "summary": "The uploaded dataset is empty, so there are no metrics to analyze yet.",
            "insights": [{
                "title": "No data available",
                "value": "0 rows",
                "description": "Upload a valid dataset to generate a dashboard.",
                "type": "info"
            }],
            "alerts": [{
                "type": "warning",
                "title": "No Dataset",
                "message": "Upload a CSV or Excel file to generate your automatic dashboard.",
                "severity": "medium"
            }],
            "recommended_questions": [
                "Which metric is most important in this dataset?",
                "What patterns stand out in the uploaded data?"
            ],
            "data_quality": {
                "score": 0,
                "missing_values": 0,
                "duplicate_rows": 0
            }
        }

    rows, total_columns = df.shape
    numeric_columns = [str(column) for column in df.select_dtypes(include=np.number).columns.tolist()]
    date_columns = [str(column) for column in _detect_date_columns(df)]
    categorical_columns = [
        str(column) for column in df.columns
        if str(column) not in numeric_columns and str(column) not in date_columns
    ]
    missing_values_total = int(df.isna().sum().sum())
    duplicate_rows = int(df.duplicated().sum())
    total_cells = rows * total_columns
    data_quality_score = round(((total_cells - missing_values_total) / total_cells) * 100, 2) if total_cells else 0

    kpis = []
    if numeric_columns:
        primary_metric = _select_metric_column(df, numeric_columns)
        if primary_metric:
            primary_series = pd.to_numeric(df[primary_metric], errors="coerce").dropna()
            if not primary_series.empty:
                sales_total = float(primary_series.sum())
                sales_avg = float(primary_series.mean())
                sales_max = float(primary_series.max())
                sales_min = float(primary_series.min())
                sales_median = float(primary_series.median())

                kpis.extend([
                    {
                        "title": f"Total {primary_metric}",
                        "value": float(sales_total),
                        "formatted_value": _format_neutral_number(sales_total),
                        "description": "Total value recorded in the dataset.",
                        "column": primary_metric,
                        "calculation": "sum"
                    },
                    {
                        "title": f"Average {primary_metric}",
                        "value": float(sales_avg),
                        "formatted_value": _format_neutral_number(sales_avg),
                        "description": "Average value across all rows.",
                        "column": primary_metric,
                        "calculation": "average"
                    },
                    {
                        "title": f"Maximum {primary_metric}",
                        "value": float(sales_max),
                        "formatted_value": _format_neutral_number(sales_max),
                        "description": "Highest recorded value in the dataset.",
                        "column": primary_metric,
                        "calculation": "max"
                    },
                    {
                        "title": f"Minimum {primary_metric}",
                        "value": float(sales_min),
                        "formatted_value": _format_neutral_number(sales_min),
                        "description": "Lowest recorded value in the dataset.",
                        "column": primary_metric,
                        "calculation": "min"
                    },
                    {
                        "title": f"Median {primary_metric}",
                        "value": float(sales_median),
                        "formatted_value": _format_neutral_number(sales_median),
                        "description": "Midpoint of the observed distribution.",
                        "column": primary_metric,
                        "calculation": "median"
                    }
                ])

        if len(numeric_columns) > 1:
            secondary_metric = next((column for column in numeric_columns if column != primary_metric), None)
            if secondary_metric:
                secondary_series = pd.to_numeric(df[secondary_metric], errors="coerce").dropna()
                if not secondary_series.empty:
                    kpis.append({
                        "title": f"Total {secondary_metric}",
                        "value": float(secondary_series.sum()),
                        "formatted_value": _format_neutral_number(float(secondary_series.sum())),
                        "description": "Secondary metric activity across the dataset.",
                        "column": secondary_metric,
                        "calculation": "sum"
                    })

    if not kpis:
        rows_kpi = {
            "title": "Dataset Rows",
            "value": int(rows),
            "formatted_value": f"{rows:,}",
            "description": "Total records available in the current dataset.",
            "column": "rows",
            "calculation": "count"
        }
        kpis.append(rows_kpi)

    kpis = kpis[:6]

    charts = []

    if date_columns and numeric_columns:
        date_column = date_columns[0]
        metric_column = _select_metric_column(df, numeric_columns)
        if metric_column:
            transformed = df[[date_column, metric_column]].copy()
            transformed[date_column] = pd.to_datetime(transformed[date_column], errors="coerce")
            transformed = transformed.dropna(subset=[date_column, metric_column]).sort_values(date_column)
            if not transformed.empty:
                transformed = transformed.assign(period=transformed[date_column].dt.to_period("M").astype(str))
                aggregated = transformed.groupby("period", as_index=False)[metric_column].sum().head(12)
                if not aggregated.empty:
                    chart_data = []
                    for _, row in aggregated.iterrows():
                        chart_data.append({
                            "name": row["period"],
                            metric_column: float(row[metric_column]),
                            "value": float(row[metric_column]),
                        })
                    charts.append({
                        "id": "chart_time_series",
                        "title": f"{metric_column} over time",
                        "description": f"Trend of {metric_column} by month.",
                        "chart_type": "line",
                        "x_axis": "period",
                        "y_axis": metric_column,
                        "aggregation": "sum",
                        "data": chart_data
                    })

    for category_column in categorical_columns[:2]:
        metric_column = None
        if numeric_columns:
            for numeric_column in numeric_columns:
                if numeric_column == category_column:
                    continue
                metric_column = numeric_column
                break
        if not metric_column:
            counts = df[category_column].fillna("Missing").astype(str).value_counts().head(10)
            chart_data = []
            for label, count in counts.items():
                chart_data.append({
                    "name": str(label),
                    "Count": int(count),
                    "value": int(count),
                })
            charts.append({
                "id": f"chart_{category_column}_count",
                "title": f"{category_column} distribution",
                "description": f"Count of records by {category_column}.",
                "chart_type": "bar",
                "x_axis": category_column,
                "y_axis": "Count",
                "aggregation": "count",
                "data": chart_data
            })
            continue

        grouped = df[[category_column, metric_column]].dropna().groupby(category_column, dropna=False)[metric_column].sum().reset_index()
        grouped = grouped.sort_values(metric_column, ascending=False).head(10)
        if grouped.empty:
            continue

        chart_data = []
        for _, row in grouped.iterrows():
            item = {
                "name": str(row[category_column]),
                metric_column: float(row[metric_column]),
                "value": float(row[metric_column]),
            }
            chart_data.append(item)

        charts.append({
            "id": f"chart_{category_column}_{metric_column}",
            "title": f"{metric_column} by {category_column}",
            "description": f"Total {metric_column} by {category_column}.",
            "chart_type": "pie" if len(chart_data) <= 6 else "bar",
            "x_axis": category_column,
            "y_axis": metric_column,
            "aggregation": "sum",
            "data": chart_data
        })

    if len(numeric_columns) >= 2:
        first_metric, second_metric = numeric_columns[0], numeric_columns[1]
        sample = df[[first_metric, second_metric]].dropna().copy()
        if not sample.empty:
            sample = sample.head(250)
            scatter_data = []
            for _, row in sample.iterrows():
                scatter_data.append({
                    "name": f"Point {len(scatter_data) + 1}",
                    first_metric: float(row[first_metric]),
                    second_metric: float(row[second_metric]),
                    "value": float(row[second_metric]),
                })
            charts.append({
                "id": "chart_scatter",
                "title": f"{first_metric} vs {second_metric}",
                "description": f"Relationship between {first_metric} and {second_metric}.",
                "chart_type": "scatter",
                "x_axis": first_metric,
                "y_axis": second_metric,
                "aggregation": "pair",
                "data": scatter_data
            })

    if not charts and numeric_columns:
        main_metric = numeric_columns[0]
        sample = df[[main_metric]].dropna().copy()
        if not sample.empty:
            sample = sample.head(15)
            chart_data = []
            for index, row in sample.reset_index(drop=True).iterrows():
                chart_data.append({
                    "name": f"Row {index + 1}",
                    main_metric: float(row[main_metric]),
                    "value": float(row[main_metric]),
                })
            charts.append({
                "id": "chart_numeric_distribution",
                "title": f"{main_metric} distribution",
                "description": f"Observed values for {main_metric}.",
                "chart_type": "bar",
                "x_axis": "Row",
                "y_axis": main_metric,
                "aggregation": "count",
                "data": chart_data
            })

    charts = charts[:8]

    if categorical_columns and numeric_columns:
        metric = _select_metric_column(df, numeric_columns)
        if metric:
            grouped = df[[categorical_columns[0], metric]].dropna().groupby(categorical_columns[0], dropna=False)[metric].sum().reset_index()
            if not grouped.empty:
                winner = grouped.sort_values(metric, ascending=False).iloc[0]
                top_category = str(winner[categorical_columns[0]])
                top_value = float(winner[metric])
            else:
                top_category = "N/A"
                top_value = 0.0
        else:
            top_category = "N/A"
            top_value = 0.0
    else:
        top_category = "N/A"
        top_value = 0.0

    correlations = []
    if len(numeric_columns) >= 2:
        corr_matrix = df[numeric_columns].corr()
        for i, column_a in enumerate(numeric_columns):
            for column_b in numeric_columns[i + 1:]:
                value = corr_matrix.loc[column_a, column_b]
                if pd.notna(value) and np.isfinite(value):
                    correlations.append({
                        "column_a": column_a,
                        "column_b": column_b,
                        "correlation": float(value)
                    })
        correlations.sort(key=lambda item: abs(item["correlation"]), reverse=True)

    strongest_correlation = None
    if correlations:
        strongest_correlation = correlations[0]

    summary_parts = [
        f"The dataset shows {rows:,} rows and {total_columns} columns.",
    ]

    if numeric_columns:
        primary_metric = _select_metric_column(df, numeric_columns)
        if primary_metric:
            primary_values = pd.to_numeric(df[primary_metric], errors="coerce").dropna()
            if not primary_values.empty:
                summary_parts.append(
                    f"The analysis indicates {primary_metric} has a total of {_format_neutral_number(float(primary_values.sum()))} and an average of {_format_neutral_number(float(primary_values.mean()))}."
                )

    if categorical_columns and top_category != "N/A":
        summary_parts.append(f"The leading category is {top_category}, which contributes the strongest observed signal in the data.")

    if date_columns:
        summary_parts.append(f"Time-based patterns are present in {date_columns[0]}, which supports trend and seasonality checks.")

    if missing_values_total > 0:
        summary_parts.append(f"There are {missing_values_total} missing values, so data completeness should be monitored.")

    summary = " ".join(summary_parts)

    insights = []
    if categorical_columns and top_category != "N/A":
        insights.append({
            "title": "Top Performer",
            "value": top_category,
            "description": f"{top_category} is the strongest contributor in the current dataset.",
            "type": "positive",
            "metric": _format_neutral_number(top_value),
        })

    if numeric_columns:
        primary_metric = _select_metric_column(df, numeric_columns)
        if primary_metric:
            values = pd.to_numeric(df[primary_metric], errors="coerce").dropna()
            if not values.empty:
                insights.append({
                    "title": "Highest Metric",
                    "value": primary_metric,
                    "description": f"{primary_metric} records the largest observed magnitude in the dataset.",
                    "type": "positive",
                    "metric": _format_neutral_number(float(values.max())),
                })

    if numeric_columns and len(numeric_columns) > 1:
        if strongest_correlation:
            insights.append({
                "title": "Strong Relationship",
                "value": f"{strongest_correlation['column_a']} ↔ {strongest_correlation['column_b']}",
                "description": "A meaningful relationship was detected between these two numeric fields.",
                "type": "insight",
                "metric": f"r = {strongest_correlation['correlation']:.2f}",
            })

    if date_columns and numeric_columns:
        date_column = date_columns[0]
        metric_column = _select_metric_column(df, numeric_columns)
        if metric_column:
            transformed = df[[date_column, metric_column]].copy()
            transformed[date_column] = pd.to_datetime(transformed[date_column], errors="coerce")
            transformed = transformed.dropna(subset=[date_column, metric_column]).sort_values(date_column)
            if not transformed.empty:
                transformed = transformed.assign(period=transformed[date_column].dt.to_period("M").astype(str))
                aggregated = transformed.groupby("period", as_index=False)[metric_column].sum().sort_values("period")
                if len(aggregated) > 1:
                    recent = aggregated.iloc[-1][metric_column]
                    previous = aggregated.iloc[-2][metric_column] if len(aggregated) > 1 else recent
                    change = ((recent - previous) / previous) * 100 if previous and previous != 0 else 0
                    insights.append({
                        "title": "Important Trend",
                        "value": f"{change:.1f}% change",
                        "description": f"{metric_column} shows a recent directional change over time.",
                        "type": "trend",
                        "metric": _format_neutral_number(float(recent)),
                    })

    if not insights:
        insights.append({
            "title": "Dataset review",
            "value": "Status OK",
            "description": "The current dataset is usable, but there are not enough signals for deeper pattern analysis.",
            "type": "info",
            "metric": f"{len(df)} rows",
        })

    alerts = []
    missing_ratio = (missing_values_total / max(total_cells, 1)) if total_cells else 0
    if missing_ratio > 0.15:
        alerts.append({
            "type": "warning",
            "title": "High Missing Values",
            "message": f"The dataset contains {missing_values_total} missing values, which may reduce analytical confidence.",
            "severity": "medium"
        })
    if duplicate_rows > 0:
        alerts.append({
            "type": "warning",
            "title": "Duplicate Records",
            "message": f"{duplicate_rows} duplicate row(s) were detected and should be reviewed before analysis.",
            "severity": "medium"
        })
    if strongest_correlation and strongest_correlation["correlation"] < -0.7:
        alerts.append({
            "type": "warning",
            "title": "Strong Negative Relationship",
            "message": f"{strongest_correlation['column_a']} and {strongest_correlation['column_b']} move in opposite directions.",
            "severity": "high"
        })
    if rows < 10:
        alerts.append({
            "type": "info",
            "title": "Limited Sample Size",
            "message": "There are not many rows in the uploaded dataset, so findings may be less stable.",
            "severity": "low"
        })
    high_cardinality_columns = []
    for column in categorical_columns:
        unique_values = df[column].nunique(dropna=True)
        if unique_values > 20:
            high_cardinality_columns.append(column)
    if high_cardinality_columns:
        alerts.append({
            "type": "warning",
            "title": "High Cardinality",
            "message": f"{', '.join(high_cardinality_columns[:3])} contains many distinct values and may be noisy for categorical grouping.",
            "severity": "medium"
        })
    if not alerts:
        alerts.append({
            "type": "success",
            "title": "Dataset is Healthy",
            "message": "No critical quality issues were detected in the uploaded dataset.",
            "severity": "low"
        })

    recommended_questions = []
    if categorical_columns and numeric_columns:
        first_category = categorical_columns[0]
        first_metric = _select_metric_column(df, numeric_columns)
        if first_category and first_metric:
            recommended_questions.append(f"Which {first_category} has the highest average {first_metric}?")
            recommended_questions.append(f"Which {first_category} contributes the most {first_metric}?")
    if date_columns and numeric_columns:
        metric = _select_metric_column(df, numeric_columns)
        if metric:
            recommended_questions.append(f"What is the trend over time for {metric}?")
    if len(numeric_columns) >= 2:
        recommended_questions.append(f"Which numeric fields show the strongest relationship in the dataset?")
    if categorical_columns:
        recommended_questions.append(f"What are the most common values in {categorical_columns[0]}?")
    if numeric_columns:
        recommended_questions.append(f"Which metric has the largest variation across the dataset?")
    if not recommended_questions:
        recommended_questions.append("What is the overall pattern in this dataset?")
        recommended_questions.append("Which fields are the most informative for analysis?")

    recommended_questions = recommended_questions[:7]

    return _json_safe({
        "status": "success",
        "dataset": {
            "rows": int(rows),
            "columns": int(total_columns),
            "numeric_columns": numeric_columns,
            "categorical_columns": categorical_columns,
            "date_columns": date_columns,
        },
        "kpis": kpis,
        "charts": charts,
        "summary": summary,
        "insights": insights,
        "alerts": alerts,
        "recommended_questions": recommended_questions,
        "data_quality": {
            "score": round(float(data_quality_score), 2),
            "missing_values": int(missing_values_total),
            "duplicate_rows": int(duplicate_rows),
        },
    })


def _build_insights_payload(df):
    if df is None or df.empty:
        return {
            "status": "success",
            "overview": {
                "data_quality_score": 0,
                "total_insights": 1,
                "critical_issues": 1,
                "opportunities": 0,
                "strong_relationships": 0,
                "rows": 0,
                "columns": 0,
                "dataset_size": "0 rows across 0 columns",
            },
            "executive_summary": "The uploaded dataset is empty, so there is no business signal to analyze yet.",
            "key_insights": [{
                "severity": "INFO",
                "title": "No Data Available",
                "explanation": "The uploaded dataset is empty. Upload a valid dataset with rows and columns to generate business insights.",
                "metric": "0 rows",
                "confidence": "Low",
                "priority": "LOW",
            }],
            "performance_insights": [],
            "category_insights": [],
            "trend_insights": [{
                "title": "No time-based column detected",
                "summary": "No time-based column was detected, so trend analysis is not available for this dataset.",
                "priority": "LOW",
            }],
            "correlation_insights": [],
            "anomaly_insights": [{
                "title": "No significant anomalies detected",
                "summary": "No dataset is available to evaluate for anomalies.",
                "priority": "LOW",
            }],
            "data_quality_insights": [{
                "title": "Dataset Empty",
                "value": "0 rows",
                "summary": "Upload a dataset with at least one row to begin analysis.",
                "priority": "LOW",
            }],
            "risks": ["No dataset is currently available for analysis."],
            "opportunities": ["Upload a valid dataset to identify business opportunities."],
            "recommendations": [{
                "title": "Upload a Dataset",
                "reason": "The current dataset is empty.",
                "action": "Add a CSV or Excel file with valid records to trigger analysis.",
                "priority": "LOW",
            }],
            "missing_values": {},
            "numeric_statistics": {},
            "date_columns": [],
            "categorical_columns": [],
        }

    rows, column_count = df.shape
    numeric_columns = df.select_dtypes(include=np.number).columns.tolist()
    categorical_columns = df.select_dtypes(exclude=np.number).columns.tolist()
    date_columns = _detect_date_columns(df)

    total_cells = rows * column_count
    missing_cells = int(df.isna().sum().sum())
    duplicate_rows = int(df.duplicated().sum())
    data_quality_score = (
        round(((total_cells - missing_cells) / total_cells) * 100, 2)
        if total_cells
        else 0
    )

    missing_values = {
        str(column): int(df[column].isna().sum())
        for column in df.columns
    }
    missing_columns = [
        column for column, count in missing_values.items()
        if count > 0
    ]
    highest_missing_column = None
    highest_missing_value = 0
    if missing_columns:
        highest_missing_column, highest_missing_value = max(
            [(column, value) for column, value in missing_values.items() if value > 0],
            key=lambda item: item[1]
        )

    numeric_stats = {}
    for column in numeric_columns:
        values = pd.to_numeric(df[column], errors="coerce").dropna()
        values = values[np.isfinite(values)]
        if values.empty:
            continue

        numeric_stats[str(column)] = {
            "average": round(float(values.mean()), 2),
            "median": round(float(values.median()), 2),
            "minimum": round(float(values.min()), 2),
            "maximum": round(float(values.max()), 2),
            "std": round(float(values.std()), 2) if len(values) > 1 else 0,
            "range": round(float(values.max() - values.min()), 2),
            "variation": round(float(values.std() / values.mean()) * 100, 2) if values.mean() != 0 else 0,
        }

    strong_correlations = []
    correlation_rows = []
    if len(numeric_columns) >= 2:
        corr_matrix = df[numeric_columns].corr()
        for index, column1 in enumerate(numeric_columns):
            for column2 in numeric_columns[index + 1:]:
                value = corr_matrix.loc[column1, column2]
                if pd.notna(value) and np.isfinite(value):
                    correlation_rows.append({
                        "column1": str(column1),
                        "column2": str(column2),
                        "correlation": round(float(value), 3),
                    })
        correlation_rows.sort(key=lambda item: abs(item["correlation"]), reverse=True)
        strong_correlations = [
            item for item in correlation_rows
            if abs(item["correlation"]) >= 0.7
        ]

    def relationship_strength(value):
        absolute_value = abs(value)
        if absolute_value >= 0.8:
            return "Very Strong"
        if absolute_value >= 0.6:
            return "Strong"
        if absolute_value >= 0.4:
            return "Moderate"
        return "Weak"

    performance_insights = []
    if numeric_stats:
        highest_avg = max(numeric_stats.items(), key=lambda item: item[1]["average"])
        lowest_avg = min(numeric_stats.items(), key=lambda item: item[1]["average"])
        most_variable = max(numeric_stats.items(), key=lambda item: abs(item[1]["std"])) if numeric_stats else (None, {"std": 0})

        for column, stats in sorted(
            numeric_stats.items(),
            key=lambda item: item[1]["average"],
            reverse=True,
        )[:5]:
            performance_insights.append({
                "title": column,
                "summary": f"Average {stats['average']} with a range of {stats['range']}.",
                "average": stats["average"],
                "median": stats["median"],
                "minimum": stats["minimum"],
                "maximum": stats["maximum"],
                "std": stats["std"],
                "range": stats["range"],
                "variation": stats["variation"],
                "priority": "HIGH" if stats["range"] >= (stats["average"] * 0.75) or stats["std"] >= max(1, stats["average"] * 0.25) else "MEDIUM",
            })

        performance_insights.insert(
            0,
            {
                "title": "Highest Average Metric",
                "summary": f"{highest_avg[0]} has the highest average value among numeric columns ({highest_avg[1]['average']}).",
                "average": highest_avg[1]["average"],
                "median": highest_avg[1]["median"],
                "minimum": highest_avg[1]["minimum"],
                "maximum": highest_avg[1]["maximum"],
                "std": highest_avg[1]["std"],
                "range": highest_avg[1]["range"],
                "variation": highest_avg[1]["variation"],
                "priority": "HIGH",
            }
        )

        performance_insights.append({
            "title": "Lowest Average Metric",
            "summary": f"{lowest_avg[0]} has the lowest average value among numeric columns ({lowest_avg[1]['average']}).",
            "average": lowest_avg[1]["average"],
            "median": lowest_avg[1]["median"],
            "minimum": lowest_avg[1]["minimum"],
            "maximum": lowest_avg[1]["maximum"],
            "std": lowest_avg[1]["std"],
            "range": lowest_avg[1]["range"],
            "variation": lowest_avg[1]["variation"],
            "priority": "MEDIUM",
        })

        if most_variable[0]:
            performance_insights.append({
                "title": "Most Variable Metric",
                "summary": f"{most_variable[0]} shows the largest variability in the dataset (std = {most_variable[1]['std']}).",
                "average": most_variable[1]["average"],
                "median": most_variable[1]["median"],
                "minimum": most_variable[1]["minimum"],
                "maximum": most_variable[1]["maximum"],
                "std": most_variable[1]["std"],
                "range": most_variable[1]["range"],
                "variation": most_variable[1]["variation"],
                "priority": "HIGH" if most_variable[1]["std"] > 0 else "LOW",
            })

    category_insights = []
    for column in categorical_columns:
        value_counts = df[column].dropna().astype(str).value_counts()
        if value_counts.empty:
            continue

        dominant = value_counts.idxmax()
        dominant_count = int(value_counts.iloc[0]) if not value_counts.empty else 0
        unique_count = int(value_counts.nunique())
        total_count = int(value_counts.sum())
        share = _safe_ratio(dominant_count, total_count)
        top_values = [
            {"category": str(value), "count": int(count), "share": _safe_ratio(count, total_count)}
            for value, count in value_counts.head(5).items()
        ]

        category_insights.append({
            "column": str(column),
            "unique_categories": unique_count,
            "dominant_category": dominant,
            "dominant_share": share,
            "top_values": top_values,
            "summary": (
                f"{dominant} is the most frequent value in {column}, accounting for {share}% of records."
                if share
                else f"{column} has {unique_count} categories with the most frequent value being {dominant}."
            ),
        })

    trend_insights = []
    if date_columns:
        date_column = date_columns[0]
        metric_column = numeric_columns[0] if numeric_columns else None
        if metric_column:
            trend_df = df[[date_column, metric_column]].dropna().copy()
            trend_df[date_column] = pd.to_datetime(trend_df[date_column], errors="coerce")
            trend_df = trend_df.dropna(subset=[date_column]).sort_values(date_column)

            if len(trend_df) >= 2:
                grouped = trend_df.groupby(date_column)[metric_column].mean().reset_index()
                grouped = grouped.rename(columns={date_column: "date", metric_column: "value"})
                grouped["label"] = grouped["date"].dt.strftime("%Y-%m-%d")
                start_value = float(grouped["value"].iloc[0])
                end_value = float(grouped["value"].iloc[-1])
                change_percent = round(((end_value - start_value) / start_value) * 100, 2) if start_value else 0
                direction = "increasing" if end_value >= start_value else "decreasing"
                trend_insights.append({
                    "title": f"{metric_column} trend over time",
                    "summary": (
                        f"The average {metric_column} is {direction} over time, changing by {change_percent}% from the earliest to latest observation."
                    ),
                    "date_column": date_column,
                    "metric_column": metric_column,
                    "change_percent": change_percent,
                    "direction": direction,
                    "points": [
                        {"label": row["label"], "value": round(float(row["value"]), 2)}
                        for _, row in grouped.head(10).iterrows()
                    ],
                    "priority": "HIGH" if abs(change_percent) >= 15 else "MEDIUM",
                })
            else:
                trend_insights.append({
                    "title": "Trend analysis limited",
                    "summary": "Insufficient time points were available to identify a reliable trend.",
                    "priority": "LOW",
                })
        else:
            trend_insights.append({
                "title": "No numeric metric for trend analysis",
                "summary": "A date column was detected, but no numeric measure was available to compare over time.",
                "priority": "LOW",
            })
    else:
        trend_insights.append({
            "title": "No time-based column detected",
            "summary": "No time-based column was detected, so trend analysis is not available for this dataset.",
            "priority": "LOW",
        })

    anomaly_insights = []
    anomaly_count = 0
    for column in numeric_columns:
        values = pd.to_numeric(df[column], errors="coerce").dropna()
        if len(values) < 3:
            continue
        mean_value = float(values.mean())
        std_value = float(values.std(ddof=0))
        if std_value == 0:
            continue
        z_scores = np.abs((values - mean_value) / std_value)
        anomalies = values[z_scores > 3]
        if not anomalies.empty:
            anomaly_count += len(anomalies)
            anomaly_insights.append({
                "column": str(column),
                "anomaly_count": int(len(anomalies)),
                "highest_value": round(float(anomalies.max()), 2),
                "severity": "HIGH" if len(anomalies) >= 2 else "MEDIUM",
            })

    if not anomaly_insights:
        anomaly_insights = [{
            "title": "No significant anomalies detected",
            "summary": "No significant anomalies were detected in the numeric columns for this dataset.",
            "priority": "LOW",
        }]

    data_type_issues = 0
    for column in df.columns:
        series = df[column]
        if pd.api.types.is_numeric_dtype(series):
            non_numeric = pd.to_numeric(series, errors='coerce').isna() & series.notna()
            data_type_issues += int(non_numeric.sum())

    data_quality_insights = [
        {
            "title": "Missing Values",
            "value": f"{missing_cells} cells",
            "summary": f"{len(missing_columns)} columns contain missing values.",
            "priority": "HIGH" if missing_cells and _safe_ratio(missing_cells, total_cells) >= 10 else "MEDIUM",
        },
        {
            "title": "Duplicates",
            "value": f"{duplicate_rows} rows",
            "summary": "Duplicate records can distort counts and comparisons.",
            "priority": "HIGH" if duplicate_rows else "LOW",
        },
        {
            "title": "Data Type Issues",
            "value": f"{data_type_issues} values",
            "summary": "Values that do not match the expected numeric type may require review.",
            "priority": "MEDIUM" if data_type_issues else "LOW",
        },
        {
            "title": "Potential Quality Risks",
            "value": f"{sum(1 for value in missing_values.values() if value > 0)} columns",
            "summary": "Columns with gaps or unusual patterns may affect downstream analysis.",
            "priority": "MEDIUM" if missing_columns else "LOW",
        },
    ]

    risk_items = []
    if missing_cells:
        missing_ratio = _safe_ratio(missing_cells, total_cells)
        if highest_missing_column and missing_ratio >= 10:
            risk_items.append(
                f"Missing values are concentrated in {highest_missing_column} ({highest_missing_value} records), which may affect reliability for key business comparisons."
            )
        else:
            risk_items.append(
                f"Missing values are present across {len(missing_columns)} columns, so a quality review is recommended before final conclusions."
            )
    if duplicate_rows:
        risk_items.append(f"{duplicate_rows} duplicate rows may distort pattern detection and aggregate metrics.")
    if data_quality_score < 80:
        risk_items.append("The overall data quality score is below 80%, which weakens confidence in the insight set.")
    if len(numeric_columns) >= 2 and correlation_rows:
        strongest_relationship = max(correlation_rows, key=lambda item: abs(item["correlation"]))
        if abs(strongest_relationship["correlation"]) < 0.4:
            risk_items.append(
                f"The strongest numeric association is only {strongest_relationship['correlation']} between {strongest_relationship['column1']} and {strongest_relationship['column2']}, suggesting weak signal strength."
            )
    if not risk_items:
        risk_items.append("No major data-quality or pattern risks were detected from the current dataset.")

    opportunities = []
    if strong_correlations:
        strongest = strong_correlations[0]
        opportunities.append(
            f"Potential opportunity: {strongest['column1']} and {strongest['column2']} show a {relationship_strength(strongest['correlation']).lower()} positive association, which may indicate a useful performance relationship worth investigating."
        )
    if categorical_columns:
        for column in categorical_columns[:2]:
            value_counts = df[column].dropna().astype(str).value_counts()
            if value_counts.empty:
                continue
            dominant = value_counts.idxmax()
            dominant_share = _safe_ratio(int(value_counts.iloc[0]), int(value_counts.sum()))
            if dominant_share >= 40:
                opportunities.append(
                    f"Potential opportunity: {column} is highly concentrated around {dominant}, which may indicate a strong segment for deeper analysis."
                )
                break
    if numeric_stats:
        top_metric = max(numeric_stats.items(), key=lambda item: item[1]["average"])
        opportunities.append(
            f"Potential opportunity: {top_metric[0]} has the highest average value and may be a strong candidate for additional forecasting and business review."
        )
    if not opportunities:
        opportunities.append("Potential opportunity: add more complete or higher-volume data to uncover stronger business opportunities.")

    recommendations = []
    if missing_columns:
        recommendations.append({
            "title": "Improve Data Completeness",
            "reason": f"{highest_missing_column} contains {highest_missing_value} missing values, which is the largest quality gap in the dataset.",
            "action": "Review source validation rules and fill or remove incomplete records before using them for analysis.",
            "priority": "HIGH",
        })
    if duplicate_rows:
        recommendations.append({
            "title": "Remove Duplicate Records",
            "reason": f"{duplicate_rows} duplicate rows may distort summary metrics and segment counts.",
            "action": "Deduplicate the source data before running dashboards or forecasts.",
            "priority": "HIGH",
        })
    if strong_correlations:
        strongest = strong_correlations[0]
        recommendations.append({
            "title": "Investigate Strong Relationships",
            "reason": f"{strongest['column1']} and {strongest['column2']} show a strong association with correlation {strongest['correlation']}.",
            "action": "Explore whether this relationship reflects a meaningful business driver or an operational pattern.",
            "priority": "MEDIUM",
        })
    if numeric_stats:
        top_metric = max(numeric_stats.items(), key=lambda item: item[1]["average"])
        recommendations.append({
            "title": f"Review {top_metric[0]} Performance",
            "reason": f"{top_metric[0]} has the highest average value among numeric columns and may drive the most business impact.",
            "action": "Compare this metric across segments and evaluate whether it is being influenced by a specific group or period.",
            "priority": "MEDIUM",
        })
    if not recommendations:
        recommendations.append({
            "title": "Monitor Dataset Health",
            "reason": "No critical issues were detected in the current data snapshot.",
            "action": "Continue validating the dataset as new records are added to maintain a reliable baseline.",
            "priority": "LOW",
        })

    key_insights = []
    if data_quality_score >= 90:
        key_insights.append({
            "severity": "POSITIVE",
            "title": "High Data Quality",
            "explanation": f"The dataset quality score is {data_quality_score}%, indicating strong completeness for analysis.",
            "metric": f"{data_quality_score}%",
            "confidence": "High",
            "priority": "HIGH",
        })
    elif data_quality_score >= 70:
        key_insights.append({
            "severity": "WARNING",
            "title": "Moderate Data Quality",
            "explanation": f"The dataset quality score is {data_quality_score}%, so some cleaning may improve reliability.",
            "metric": f"{data_quality_score}%",
            "confidence": "Moderate",
            "priority": "MEDIUM",
        })
    else:
        key_insights.append({
            "severity": "CRITICAL",
            "title": "Data Quality Risk",
            "explanation": f"The dataset quality score is {data_quality_score}%, which reduces confidence in analytical results.",
            "metric": f"{data_quality_score}%",
            "confidence": "High",
            "priority": "HIGH",
        })

    if missing_values:
        highest_missing = max(missing_values.items(), key=lambda item: item[1])
        key_insights.append({
            "severity": "WARNING",
            "title": "Missing Data Concentration",
            "explanation": f"{highest_missing[0]} contains {highest_missing[1]} missing records, which may limit analysis for that attribute.",
            "metric": f"{_safe_ratio(highest_missing[1], rows)}% of rows",
            "confidence": "High",
            "priority": "HIGH" if highest_missing[1] > max(1, rows * 0.1) else "MEDIUM",
        })

    if strong_correlations:
        strongest = strong_correlations[0]
        key_insights.append({
            "severity": "OPPORTUNITY",
            "title": "Strong Numeric Association",
            "explanation": f"{strongest['column1']} and {strongest['column2']} show a {relationship_strength(strongest['correlation']).lower()} association (r = {strongest['correlation']}). This indicates a meaningful co-movement pattern, though not causation.",
            "metric": f"r = {strongest['correlation']}",
            "confidence": relationship_strength(strongest['correlation']),
            "priority": "HIGH" if abs(strongest['correlation']) >= 0.8 else "MEDIUM",
        })

    if numeric_stats:
        highest_metric = max(numeric_stats.items(), key=lambda item: item[1]["average"])
        key_insights.append({
            "severity": "POSITIVE",
            "title": "Highest Average Metric",
            "explanation": f"{highest_metric[0]} has the highest mean value in the dataset, suggesting strong relative contribution or scale.",
            "metric": f"Avg = {highest_metric[1]['average']}",
            "confidence": "High",
            "priority": "MEDIUM",
        })

    if anomaly_count:
        key_insights.append({
            "severity": "CRITICAL",
            "title": "Potential Outliers",
            "explanation": f"{anomaly_count} unusually high or low values were detected and may deserve review.",
            "metric": f"{anomaly_count} anomalies",
            "confidence": "Medium",
            "priority": "HIGH",
        })

    if not key_insights:
        key_insights.append({
            "severity": "INFO",
            "title": "Limited Insight Available",
            "explanation": "The dataset does not contain enough variation to produce additional findings.",
            "metric": "N/A",
            "confidence": "Low",
            "priority": "LOW",
        })

    top_category_label = None
    if categorical_columns:
        category_candidates = []
        for column in categorical_columns:
            value_counts = df[column].dropna().astype(str).value_counts()
            if value_counts.empty:
                continue
            category_candidates.append({
                "column": str(column),
                "count": int(value_counts.iloc[0]),
            })
        if category_candidates:
            top_category_label = max(category_candidates, key=lambda item: item["count"])["column"]

    return {
        "status": "success",
        "overview": {
            "data_quality_score": round(data_quality_score, 2),
            "total_insights": len(key_insights),
            "critical_issues": sum(1 for item in key_insights if item.get("severity") in {"CRITICAL", "WARNING"}) + (1 if duplicate_rows or missing_cells else 0),
            "opportunities": len(opportunities),
            "strong_relationships": len(strong_correlations),
            "rows": rows,
            "columns": column_count,
            "dataset_size": f"{rows:,} rows across {column_count} columns",
        },
        "executive_summary": (
            f"The dataset contains {rows:,} rows across {column_count} columns. Overall data quality is {data_quality_score}%. "
            f"{len(numeric_columns)} numeric metrics and {len(categorical_columns)} categorical dimensions were analyzed, with "
            f"{len(missing_columns)} columns showing missing values and {duplicate_rows} duplicated rows. "
            + (
                f"The strongest relationship is between {strong_correlations[0]['column1']} and {strong_correlations[0]['column2']} with a correlation of {strong_correlations[0]['correlation']}. "
                if strong_correlations else "No high-confidence numeric relationship was detected. "
            )
            + (
                f"The most variable metric is {max(numeric_stats.items(), key=lambda item: item[1]['std'])[0]} and the top category distribution is concentrated in {top_category_label} when relevant."
                if numeric_stats and top_category_label else ""
            )
        ),
        "key_insights": key_insights,
        "performance_insights": performance_insights,
        "category_insights": category_insights,
        "trend_insights": trend_insights,
        "correlation_insights": [
            {
                "title": "Strongest Positive Relationship",
                "detail": (
                    f"{item['column1']} and {item['column2']} show a strong positive association (r = {item['correlation']}). This indicates that higher values in one metric tend to appear with higher values in the other, but it does not establish causation."
                    if item["correlation"] >= 0 else ""
                ),
                "correlation": item["correlation"],
                "strength": relationship_strength(item["correlation"]),
                "priority": "HIGH" if abs(item["correlation"]) >= 0.8 else "MEDIUM",
            }
            for item in (strong_correlations[:1] if strong_correlations else [])
        ] + [
            {
                "title": "Strongest Negative Relationship",
                "detail": (
                    f"{item['column1']} and {item['column2']} show a negative association (r = {item['correlation']}). This indicates that higher values in one metric tend to appear with lower values in the other, but it does not establish causation."
                ),
                "correlation": item["correlation"],
                "strength": relationship_strength(item["correlation"]),
                "priority": "MEDIUM" if abs(item["correlation"]) >= 0.5 else "LOW",
            }
            for item in sorted(correlation_rows, key=lambda item: item["correlation"])[:1]
        ],
        "anomaly_insights": anomaly_insights,
        "data_quality_insights": data_quality_insights,
        "risks": risk_items,
        "opportunities": opportunities,
        "recommendations": recommendations,
        "missing_values": missing_values,
        "numeric_statistics": numeric_stats,
        "date_columns": date_columns,
        "categorical_columns": [str(column) for column in categorical_columns],
    }


# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.post("/register")
def register_user(data: RegisterRequest):

    email = data.email.strip().lower()
    name = data.name.strip()

    if not name:
        raise HTTPException(
            status_code=400,
            detail="Name is required."
        )

    if not email:
        raise HTTPException(
            status_code=400,
            detail="Email is required."
        )

    if len(data.password) < 6:
        raise HTTPException(
            status_code=400,
            detail="Password must be at least 6 characters."
        )

    # Check if user already exists
    existing_user = users_db.find_one({
        "email": email
    })

    if existing_user:
        raise HTTPException(
            status_code=400,
            detail="User already exists."
        )

    # Create new user
    new_user = {
        "name": name,
        "email": email,
        "password": hash_password(data.password)
    }

    users_db.insert_one(new_user)

    return {
        "status": "success",
        "message": "Registration successful."
    }
@app.post("/login")
def login_user(data: LoginRequest):

    email = data.email.strip().lower()

    # Find user in MongoDB
    user = users_db.find_one({
        "email": email
    })

    if not user:
        raise HTTPException(
            status_code=401,
            detail="Invalid email or password."
        )

    # Verify password
    if not verify_password(
        data.password,
        user["password"]
    ):
        raise HTTPException(
            status_code=401,
            detail="Invalid email or password."
        )

    # Create JWT token
    access_token = create_access_token({
        "sub": email,
        "name": user["name"]
    })

    return {
        "status": "success",
        "message": "Login successful.",
        "access_token": access_token,
        "token_type": "bearer",
        "user": {
            "name": user["name"],
            "email": user["email"]
        }
    }
    # =========================
# Current User Authentication
# =========================

def get_current_user(
    authorization: str = Header(None)
):
    if not authorization:
        raise HTTPException(
            status_code=401,
            detail="Authentication required."
        )

    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail="Invalid authorization header."
        )

    token = authorization.split(" ", 1)[1]

    try:
        payload = jwt.decode(
            token,
            SECRET_KEY,
            algorithms=[ALGORITHM]
        )

        email = payload.get("sub")

        if not email:
            raise HTTPException(
                status_code=401,
                detail="Invalid token."
            )

        return email

    except JWTError:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired token."
        )
@app.get("/")
def root():
    return {
        "message": "AI Business Analyst API is running",
        "status": "success"
    }


@app.get("/health")
def health_check():
    return {
        "status": "healthy"
    }


@app.get("/auto-dashboard")
def get_auto_dashboard(
    current_user: str = Depends(get_current_user)
):
    user_data = user_datasets.get(current_user)

    if not user_data:
        raise HTTPException(
            status_code=400,
            detail="Please upload a dataset first."
        )

    df = user_data["df"].copy()
    if df.empty:
        raise HTTPException(
            status_code=400,
            detail="Please upload a dataset first."
        )

    return _build_auto_dashboard_payload(df)


@app.get("/ai-analysis")
def get_ai_analysis(
    current_user: str = Depends(get_current_user)
):
    user_data = user_datasets.get(current_user)

    if not user_data:
        raise HTTPException(
            status_code=400,
            detail="Please upload a dataset first."
        )

    try:
        df = user_data["df"]
        rows, column_count = df.shape
        numeric_columns = df.select_dtypes(
            include=np.number
        ).columns.tolist()
        categorical_columns = df.select_dtypes(
            exclude=np.number
        ).columns.tolist()

        total_cells = rows * column_count
        missing_cells = int(df.isna().sum().sum())
        duplicate_rows = int(df.duplicated().sum())
        data_quality_score = (
            round((total_cells - missing_cells) / total_cells * 100, 2)
            if total_cells
            else 0
        )

        numeric_statistics = {}
        for column in numeric_columns:
            values = pd.to_numeric(df[column], errors="coerce").dropna()
            values = values[np.isfinite(values)]
            if values.empty:
                continue

            numeric_statistics[str(column)] = {
                "average": round(float(values.mean()), 2),
                "minimum": round(float(values.min()), 2),
                "maximum": round(float(values.max()), 2),
                "median": round(float(values.median()), 2),
                "std": round(float(values.std()), 2) if len(values) > 1 else 0,
            }

        highest_average = None
        lowest_average = None
        if numeric_statistics:
            highest_column = max(
                numeric_statistics,
                key=lambda column: numeric_statistics[column]["average"]
            )
            lowest_column = min(
                numeric_statistics,
                key=lambda column: numeric_statistics[column]["average"]
            )
            highest_average = {
                "column": highest_column,
                "value": numeric_statistics[highest_column]["average"],
            }
            lowest_average = {
                "column": lowest_column,
                "value": numeric_statistics[lowest_column]["average"],
            }

        missing_analysis = []
        for column in df.columns:
            count = int(df[column].isna().sum())
            if count:
                missing_analysis.append({
                    "column": str(column),
                    "count": count,
                    "percentage": round(count / rows * 100, 2) if rows else 0,
                })
        missing_analysis.sort(key=lambda item: item["count"], reverse=True)

        correlations = []
        if len(numeric_columns) >= 2:
            correlation_matrix = df[numeric_columns].corr()
            for index, column1 in enumerate(numeric_columns):
                for column2 in numeric_columns[index + 1:]:
                    value = correlation_matrix.loc[column1, column2]
                    if pd.notna(value) and np.isfinite(value):
                        correlations.append({
                            "column1": str(column1),
                            "column2": str(column2),
                            "correlation": round(float(value), 3),
                        })
        correlations.sort(
            key=lambda item: abs(item["correlation"]),
            reverse=True
        )
        strong_correlations = [
            item for item in correlations
            if abs(item["correlation"]) >= 0.7
        ]

        category_analysis = []
        for column in categorical_columns:
            counts = (
                df[column].dropna().astype(str).value_counts().head(5)
            )
            if not counts.empty:
                category_analysis.append({
                    "column": str(column),
                    "top_values": [
                        {"value": value, "count": int(count)}
                        for value, count in counts.items()
                    ],
                })

        key_findings = []
        if data_quality_score >= 90:
            key_findings.append({
                "type": "positive",
                "title": "Strong Data Quality",
                "description": (
                    f"The dataset has an overall data quality score of "
                    f"{data_quality_score}%."
                ),
            })
        elif data_quality_score >= 70:
            key_findings.append({
                "type": "warning",
                "title": "Moderate Data Quality",
                "description": (
                    f"The dataset has a data quality score of "
                    f"{data_quality_score}%. Some cleaning may be required."
                ),
            })
        else:
            key_findings.append({
                "type": "danger",
                "title": "Data Quality Needs Attention",
                "description": (
                    f"The dataset has a data quality score of "
                    f"{data_quality_score}%. Data cleaning is recommended."
                ),
            })

        if highest_average:
            key_findings.append({
                "type": "positive",
                "title": "Highest Average Metric",
                "description": (
                    f"{highest_average['column']} has the highest average "
                    f"value among numeric columns ({highest_average['value']})."
                ),
            })
            key_findings.append({
                "type": "info",
                "title": "Lowest Average Metric",
                "description": (
                    f"{lowest_average['column']} has the lowest average "
                    f"value among numeric columns ({lowest_average['value']})."
                ),
            })

        if duplicate_rows:
            key_findings.append({
                "type": "warning",
                "title": "Duplicate Records",
                "description": f"{duplicate_rows} duplicate records were detected.",
            })
        else:
            key_findings.append({
                "type": "positive",
                "title": "No Duplicate Records",
                "description": "No duplicate rows were detected in the uploaded dataset.",
            })

        if missing_analysis:
            top_missing = missing_analysis[0]
            key_findings.append({
                "type": "warning",
                "title": "Missing Values Detected",
                "description": (
                    f"{top_missing['column']} contains {top_missing['count']} "
                    f"missing values ({top_missing['percentage']}%)."
                ),
            })

        risks = []
        if data_quality_score < 90:
            risks.append(
                "Dataset quality is below the ideal level and should be "
                "reviewed before making important business decisions."
            )
        if duplicate_rows:
            risks.append(
                f"{duplicate_rows} duplicate records may affect analytical accuracy."
            )
        if missing_analysis:
            risks.append(
                f"Missing values were detected in {len(missing_analysis)} columns."
            )
        if not risks:
            risks.append("No major data-quality risks were detected from the current dataset.")

        opportunities = []
        if strong_correlations:
            strongest = strong_correlations[0]
            opportunities.append(
                f"A strong relationship exists between {strongest['column1']} "
                f"and {strongest['column2']} (correlation: "
                f"{strongest['correlation']})."
            )
        if categorical_columns:
            opportunities.append(
                "Categorical dimensions can be used for segmentation and performance comparison."
            )
        if numeric_columns:
            opportunities.append(
                "Numeric metrics can be used for trend analysis and forecasting."
            )
        if not opportunities:
            opportunities.append(
                "Upload a richer dataset to identify additional business opportunities."
            )

        recommendations = []
        if missing_analysis:
            recommendations.append(
                "Review and clean missing values before performing advanced analysis."
            )
        if duplicate_rows:
            recommendations.append(
                "Remove or investigate duplicate records to improve analytical accuracy."
            )
        if strong_correlations:
            recommendations.append(
                "Investigate strongly correlated metrics to understand possible business relationships."
            )
        if categorical_columns:
            recommendations.append(
                "Compare performance across categorical segments to identify high and low performers."
            )
        recommendations.append(
            "Use forecasting on relevant numeric metrics to support future planning."
        )

        summary_parts = [
            f"The dataset contains {rows:,} rows and {column_count} columns.",
            f"It includes {len(numeric_columns)} numeric and "
            f"{len(categorical_columns)} categorical columns.",
            f"The overall data quality score is {data_quality_score}%.",
        ]
        if duplicate_rows:
            summary_parts.append(f"{duplicate_rows} duplicate records were detected.")
        if strong_correlations:
            strongest = strong_correlations[0]
            summary_parts.append(
                f"The strongest detected relationship is between "
                f"{strongest['column1']} and {strongest['column2']}."
            )

        return {
            "status": "success",
            "overview": {
                "rows": rows,
                "columns": column_count,
                "numeric_columns": len(numeric_columns),
                "categorical_columns": len(categorical_columns),
                "data_quality_score": data_quality_score,
                "duplicate_rows": duplicate_rows,
                "missing_cells": missing_cells,
            },
            "executive_summary": " ".join(summary_parts),
            "key_findings": key_findings,
            "risks": risks,
            "opportunities": opportunities,
            "recommendations": recommendations,
            "missing_analysis": missing_analysis[:10],
            "correlations": correlations[:10],
            "strong_correlations": strong_correlations[:5],
            "category_analysis": category_analysis[:10],
            "numeric_statistics": numeric_statistics,
        }
    except HTTPException:
        raise
    except Exception as error:
        print("AI Analysis error:", error)
        raise HTTPException(
            status_code=500,
            detail="Unable to generate AI analysis."
        ) from error


@app.post("/ask-ai")
def ask_ai(
    data: AIAnalysisQuestion,
    current_user: str = Depends(get_current_user)
):

    user_data = user_datasets.get(current_user)

    if not user_data:
        raise HTTPException(
            status_code=400,
            detail="Please upload a dataset first."
        )

    df = user_data["df"]

    question = data.question.strip()

    if not question:
        raise HTTPException(
            status_code=400,
            detail="Please enter a question."
        )

    question_lower = question.lower()

     

    # Basic dataset information
    rows = len(df)
    columns = len(df.columns)

    numeric_columns = (
        df.select_dtypes(include="number")
        .columns
        .tolist()
    )

    categorical_columns = (
        df.select_dtypes(
            include=["object", "category"]
        )
        .columns
        .tolist()
    )

    # Missing values
    missing_values = {
        column: int(value)
        for column, value in df.isnull().sum().items()
        if value > 0
    }

    # Data quality
    total_cells = rows * columns

    if total_cells > 0:
        missing_cells = int(df.isnull().sum().sum())
        quality = round(
            ((total_cells - missing_cells) / total_cells) * 100,
            2
        )
    else:
        quality = 0

    # Highest / lowest averages
    averages = {}

    for column in numeric_columns:
        series = pd.to_numeric(
            df[column],
            errors="coerce"
        ).dropna()

        if len(series) > 0:
            averages[column] = float(series.mean())

    highest_average = None
    lowest_average = None

    if averages:
        highest_column = max(
            averages,
            key=averages.get
        )

        lowest_column = min(
            averages,
            key=averages.get
        )

        highest_average = {
            "column": highest_column,
            "value": round(
                averages[highest_column],
                2
            )
        }

        lowest_average = {
            "column": lowest_column,
            "value": round(
                averages[lowest_column],
                2
            )
        }

    # Strongest correlation
    strongest_relationship = None

    if len(numeric_columns) >= 2:
        correlation_matrix = df[numeric_columns].corr()

        strongest_value = 0
        strongest_pair = None

        for i in range(len(numeric_columns)):
            for j in range(i + 1, len(numeric_columns)):
                value = correlation_matrix.iloc[i, j]

                if pd.notna(value) and abs(value) > abs(strongest_value):
                    strongest_value = float(value)
                    strongest_pair = (
                        numeric_columns[i],
                        numeric_columns[j]
                    )

        if strongest_pair:
            strongest_relationship = {
                "columns": list(strongest_pair),
                "correlation": round(
                    strongest_value,
                    2
                )
            }
    answer = None

    # Column-specific questions
    mentioned_column = None

    for column in numeric_columns:
        if column.lower() in question_lower:
            mentioned_column = column
            break

    if mentioned_column:
        column_series = pd.to_numeric(
            df[mentioned_column],
            errors="coerce"
        ).dropna()

        if len(column_series) > 0:

            if "average" in question_lower or "mean" in question_lower:
                answer = (
                    f"The average of {mentioned_column} is "
                    f"{column_series.mean():,.2f}."
                )

            elif "maximum" in question_lower or "max" in question_lower:
                answer = (
                    f"The maximum value of {mentioned_column} is "
                    f"{column_series.max():,.2f}."
                )

            elif "minimum" in question_lower or "min" in question_lower:
                answer = (
                    f"The minimum value of {mentioned_column} is "
                    f"{column_series.min():,.2f}."
                )

            elif "median" in question_lower:
                answer = (
                    f"The median of {mentioned_column} is "
                    f"{column_series.median():,.2f}."
                )

            else:
                answer = (
                    f"{mentioned_column} contains "
                    f"{len(column_series):,} valid numeric values. "
                    f"Its average is {column_series.mean():,.2f}, "
                    f"minimum is {column_series.min():,.2f}, "
                    f"and maximum is {column_series.max():,.2f}."
                )
    # Categorical column questions
    mentioned_categorical_column = None

    for column in categorical_columns:
        if column.lower() in question_lower:
            mentioned_categorical_column = column
            break

    if mentioned_categorical_column:
        column_series = df[mentioned_categorical_column].dropna()

        if len(column_series) > 0:

            value_counts = column_series.value_counts()

            most_common = value_counts.index[0]
            most_common_count = int(value_counts.iloc[0])

            if any(
                word in question_lower
                for word in [
                    "common",
                    "popular",
                    "frequent",
                    "most"
                ]
            ):
                answer = (
                    f"The most common value in "
                    f"{mentioned_categorical_column} is "
                    f"'{most_common}', appearing "
                    f"{most_common_count:,} times."
                )

            elif any(
                word in question_lower
                for word in [
                    "category",
                    "categories",
                    "values",
                    "unique"
                ]
            ):
                unique_values = column_series.nunique()

                top_values = ", ".join(
                    str(value)
                    for value in value_counts.head(5).index
                )

                answer = (
                    f"The {mentioned_categorical_column} column "
                    f"has {unique_values:,} unique values. "
                    f"The most frequent values are: "
                    f"{top_values}."
                )

            else:
                unique_values = column_series.nunique()

                answer = (
                    f"The {mentioned_categorical_column} column "
                    f"contains {unique_values:,} unique values. "
                    f"The most common value is "
                    f"'{most_common}', appearing "
                    f"{most_common_count:,} times."
                )
    # Question-based answers
    if any(
        word in question_lower
        for word in [
            "row",
            "rows",
            "record",
            "records"
        ]
    ):
        answer = (
            f"The dataset contains {rows:,} rows "
            f"and {columns} columns."
        )

    elif any(
        word in question_lower
        for word in [
            "missing",
            "null",
            "empty"
        ]
    ):
        if missing_values:
            missing_text = ", ".join(
                f"{column}: {count}"
                for column, count
                in missing_values.items()
            )

            answer = (
                f"Missing values were found in "
                f"{len(missing_values)} column(s): "
                f"{missing_text}."
            )
        else:
            answer = "No missing values were detected."

    elif any(
        word in question_lower
        for word in [
            "quality",
            "clean",
            "data quality"
        ]
    ):
        answer = (
            f"The dataset has a data quality score "
            f"of {quality}%."
        )

    elif any(
        word in question_lower
        for word in [
            "highest",
            "maximum",
            "largest"
        ]
    ) and highest_average:

        answer = (
            f"{highest_average['column']} has the highest "
            f"average value at "
            f"{highest_average['value']:,.2f}."
        )

    elif any(
        word in question_lower
        for word in [
            "lowest",
            "minimum",
            "smallest"
        ]
    ) and lowest_average:

        answer = (
            f"{lowest_average['column']} has the lowest "
            f"average value at "
            f"{lowest_average['value']:,.2f}."
        )

    elif any(
        word in question_lower
        for word in [
            "correlation",
            "relationship",
            "related"
        ]
    ):
        if strongest_relationship:
            answer = (
                f"The strongest relationship is between "
                f"{strongest_relationship['columns'][0]} "
                f"and "
                f"{strongest_relationship['columns'][1]}, "
                f"with a correlation of "
                f"{strongest_relationship['correlation']}."
            )
        else:
            answer = (
                "There are not enough numeric columns "
                "to calculate a relationship."
            )

    elif any(
        word in question_lower
        for word in [
            "numeric",
            "number"
        ]
    ):
        answer = (
            f"The dataset contains {len(numeric_columns)} "
            f"numeric column(s): "
            f"{', '.join(numeric_columns)}."
        )

    elif any(
        word in question_lower
        for word in [
            "categorical",
            "category",
            "categories"
        ]
    ):
        answer = (
            f"The dataset contains "
            f"{len(categorical_columns)} categorical "
            f"column(s): "
            f"{', '.join(categorical_columns) if categorical_columns else 'None'}."
        )

    elif any(
        word in question_lower
        for word in [
            "summary",
            "overview",
            "analyze",
            "analysis"
        ]
    ):
        answer = (
            f"Dataset summary: {rows:,} rows, "
            f"{columns} columns, "
            f"{len(numeric_columns)} numeric columns, "
            f"{len(categorical_columns)} categorical columns, "
            f"and a data quality score of {quality}%."
        )

    else:
        if answer is None:
            answer = (
                "I can answer questions about your dataset's "
                "rows, columns, missing values, data quality, "
                "numeric metrics, averages, and correlations."
            )

    return {
        "status": "success",
        "question": question,
        "answer": answer
    }
# ============================================================
# INSIGHTS MODULE
# ============================================================

@app.get("/insights")
def get_insights(
    current_user: str = Depends(get_current_user)
):
    user_data = user_datasets.get(current_user)

    if not user_data:
        raise HTTPException(
            status_code=400,
            detail="Please upload a dataset first."
        )

    df = user_data["df"].copy()
    anomalies = user_data.get("anomalies", [])

    if df.empty:
        raise HTTPException(
            status_code=400,
            detail="The uploaded dataset is empty."
        )

    # --------------------------------------------------------
    # BASIC DATA INFORMATION
    # --------------------------------------------------------

    rows = len(df)
    columns = len(df.columns)

    numeric_columns = df.select_dtypes(
        include=np.number
    ).columns.tolist()

    categorical_columns = df.select_dtypes(
        exclude=np.number
    ).columns.tolist()

    total_cells = rows * columns

    missing_cells = int(
        df.isna().sum().sum()
    )

    duplicate_rows = int(
        df.duplicated().sum()
    )

    if total_cells > 0:
        data_quality_score = round(
            max(
                0,
                (
                    1
                    - (
                        missing_cells / total_cells
                    )
                    - (
                        duplicate_rows / max(rows, 1)
                    )
                )
                * 100
            ),
            1
        )
    else:
        data_quality_score = 0

    # --------------------------------------------------------
    # OVERVIEW COUNTERS
    # --------------------------------------------------------

    total_insights = 0
    critical_issues = 0
    opportunities = 0
    strong_relationships = 0

    # --------------------------------------------------------
    # EXECUTIVE SUMMARY
    # --------------------------------------------------------

    executive_points = []

    executive_points.append(
        f"The dataset contains {rows:,} rows across "
        f"{columns} columns."
    )

    if numeric_columns:
        executive_points.append(
            f"{len(numeric_columns)} numeric columns are "
            f"available for quantitative analysis."
        )

    if categorical_columns:
        executive_points.append(
            f"{len(categorical_columns)} categorical columns "
            f"are available for segmentation analysis."
        )

    if data_quality_score >= 90:
        quality_message = (
            "Overall data quality is strong and suitable "
            "for business analysis."
        )
    elif data_quality_score >= 70:
        quality_message = (
            "Overall data quality is acceptable, but some "
            "cleaning may improve analytical reliability."
        )
    else:
        quality_message = (
            "Data quality requires attention before relying "
            "heavily on analytical conclusions."
        )

    executive_points.append(quality_message)

    # --------------------------------------------------------
    # KEY INSIGHTS
    # --------------------------------------------------------

    key_insights = []

    # Highest / lowest averages
    average_values = {}

    for column in numeric_columns:
        try:
            value = df[column].mean()

            if pd.notna(value):
                average_values[column] = float(value)

        except Exception:
            continue

    if average_values:
        highest_column = max(
            average_values,
            key=average_values.get
        )

        lowest_column = min(
            average_values,
            key=average_values.get
        )

        highest_value = average_values[highest_column]
        lowest_value = average_values[lowest_column]

        key_insights.append({
            "type": "performance",
            "priority": "High",
            "title": "Highest Average Metric",
            "description": (
                f"{highest_column} has the highest average "
                f"value of {highest_value:,.2f}."
            ),
            "metric": f"{highest_value:,.2f}",
            "column": highest_column
        })

        key_insights.append({
            "type": "performance",
            "priority": "Medium",
            "title": "Lowest Average Metric",
            "description": (
                f"{lowest_column} has the lowest average "
                f"value of {lowest_value:,.2f}."
            ),
            "metric": f"{lowest_value:,.2f}",
            "column": lowest_column
        })

        total_insights += 2

    # --------------------------------------------------------
    # PERFORMANCE INSIGHTS
    # --------------------------------------------------------

    performance_insights = []

    for column in numeric_columns:

        try:
            mean_value = df[column].mean()
            median_value = df[column].median()
            min_value = df[column].min()
            max_value = df[column].max()

            if pd.isna(mean_value):
                continue

            performance_insights.append({
                "column": column,
                "average": round(float(mean_value), 2),
                "median": round(float(median_value), 2)
                if pd.notna(median_value)
                else None,
                "minimum": round(float(min_value), 2)
                if pd.notna(min_value)
                else None,
                "maximum": round(float(max_value), 2)
                if pd.notna(max_value)
                else None
            })

        except Exception:
            continue

    # --------------------------------------------------------
    # CATEGORY INSIGHTS
    # --------------------------------------------------------

    category_insights = []

    for column in categorical_columns[:10]:

        try:
            value_counts = (
                df[column]
                .dropna()
                .astype(str)
                .value_counts()
                .head(5)
            )

            if value_counts.empty:
                continue

            top_value = value_counts.index[0]
            top_count = int(value_counts.iloc[0])

            category_insights.append({
                "column": column,
                "top_category": top_value,
                "count": top_count,
                "categories": [
                    {
                        "name": str(index),
                        "count": int(value)
                    }
                    for index, value
                    in value_counts.items()
                ]
            })

            total_insights += 1

        except Exception:
            continue

    # --------------------------------------------------------
    # CORRELATION INSIGHTS
    # --------------------------------------------------------

    correlation_insights = []

    if len(numeric_columns) >= 2:

        try:
            correlation_matrix = df[
                numeric_columns
            ].corr()

            for i in range(
                len(numeric_columns)
            ):
                for j in range(
                    i + 1,
                    len(numeric_columns)
                ):

                    col1 = numeric_columns[i]
                    col2 = numeric_columns[j]

                    correlation = correlation_matrix.loc[
                        col1,
                        col2
                    ]

                    if pd.notna(correlation):

                        correlation_value = float(
                            correlation
                        )

                        if abs(correlation_value) >= 0.7:

                            if correlation_value > 0:
                                relationship = "Positive"
                            else:
                                relationship = "Negative"

                            correlation_insights.append({
                                "column_a": col1,
                                "column_b": col2,
                                "correlation": round(
                                    correlation_value,
                                    3
                                ),
                                "relationship": relationship,
                                "strength": (
                                    "Strong"
                                    if abs(correlation_value) >= 0.8
                                    else "Moderate"
                                )
                            })

                            strong_relationships += 1
                            total_insights += 1

        except Exception:
            pass

    # --------------------------------------------------------
    # DATA QUALITY INSIGHTS
    # --------------------------------------------------------

    data_quality_insights = []

    if missing_cells > 0:

        missing_by_column = (
            df.isna()
            .sum()
            .sort_values(
                ascending=False
            )
        )

        for column, count in missing_by_column.items():

            if count <= 0:
                continue

            percentage = (
                count / rows
            ) * 100

            data_quality_insights.append({
                "type": "missing",
                "priority": (
                    "High"
                    if percentage >= 20
                    else "Medium"
                ),
                "column": column,
                "count": int(count),
                "percentage": round(
                    percentage,
                    2
                ),
                "message": (
                    f"{column} contains {int(count):,} "
                    f"missing values "
                    f"({percentage:.1f}% of rows)."
                )
            })

            total_insights += 1

            if percentage >= 20:
                critical_issues += 1

    if duplicate_rows > 0:

        duplicate_percentage = (
            duplicate_rows / rows
        ) * 100

        data_quality_insights.append({
            "type": "duplicate",
            "priority": (
                "High"
                if duplicate_percentage >= 10
                else "Medium"
            ),
            "column": None,
            "count": duplicate_rows,
            "percentage": round(
                duplicate_percentage,
                2
            ),
            "message": (
                f"{duplicate_rows:,} duplicate rows "
                f"were detected."
            )
        })

        total_insights += 1

        if duplicate_percentage >= 10:
            critical_issues += 1

    if not data_quality_insights:

        data_quality_insights.append({
            "type": "quality",
            "priority": "Low",
            "column": None,
            "count": 0,
            "percentage": 0,
            "message": (
                "No major missing-value or duplicate-row "
                "issues were detected."
            )
        })

    # --------------------------------------------------------
    # ANOMALY INSIGHTS
    # --------------------------------------------------------

    anomaly_insights = []

    if anomalies:

        anomaly_count = len(anomalies)

        anomaly_insights.append({
            "priority": "High",
            "title": "Potential Anomalies Detected",
            "count": anomaly_count,
            "message": (
                f"{anomaly_count:,} potential anomalous "
                f"records were detected in the dataset."
            )
        })

        total_insights += 1
        critical_issues += 1

    else:

        anomaly_insights.append({
            "priority": "Low",
            "title": "No Major Anomalies",
            "count": 0,
            "message": (
                "No major anomalies were detected "
                "by the current analysis."
            )
        })

    # --------------------------------------------------------
    # TREND INSIGHTS
    # --------------------------------------------------------

    trend_insights = []

    # Try to identify a year/date column
    date_column = None

    for column in df.columns:

        column_name = str(column).lower()

        if (
            "date" in column_name
            or "year" in column_name
            or "time" in column_name
        ):
            date_column = column
            break

    if date_column and numeric_columns:

        try:

            temp_df = df[
                [date_column] + numeric_columns
            ].copy()

            temp_df[date_column] = pd.to_numeric(
                temp_df[date_column],
                errors="coerce"
            )

            temp_df = temp_df.dropna(
                subset=[date_column]
            )

            if len(temp_df) >= 3:

                first_period = temp_df[
                    date_column
                ].min()

                last_period = temp_df[
                    date_column
                ].max()

                for column in numeric_columns[:5]:

                    start_value = temp_df[
                        temp_df[date_column]
                        == first_period
                    ][column].mean()

                    end_value = temp_df[
                        temp_df[date_column]
                        == last_period
                    ][column].mean()

                    if (
                        pd.notna(start_value)
                        and pd.notna(end_value)
                    ):

                        change = (
                            end_value
                            - start_value
                        )

                        if start_value != 0:
                            change_percent = (
                                change
                                / abs(start_value)
                            ) * 100
                        else:
                            change_percent = 0

                        if change > 0:
                            direction = "Increasing"
                        elif change < 0:
                            direction = "Decreasing"
                        else:
                            direction = "Stable"

                        trend_insights.append({
                            "column": column,
                            "start_period": str(
                                first_period
                            ),
                            "end_period": str(
                                last_period
                            ),
                            "start_value": round(
                                float(start_value),
                                2
                            ),
                            "end_value": round(
                                float(end_value),
                                2
                            ),
                            "change_percent": round(
                                float(change_percent),
                                2
                            ),
                            "direction": direction
                        })

                        total_insights += 1

        except Exception:
            pass

    if not trend_insights:

        trend_insights.append({
            "column": None,
            "direction": "Unavailable",
            "change_percent": None,
            "message": (
                "A reliable time-based trend could not "
                "be identified from the uploaded dataset."
            )
        })

    # --------------------------------------------------------
    # RISKS
    # --------------------------------------------------------

    risks = []

    if data_quality_score < 70:

        risks.append({
            "priority": "High",
            "title": "Data Quality Risk",
            "description": (
                "Low data quality may affect the reliability "
                "of business analysis."
            )
        })

    if missing_cells > 0:

        risks.append({
            "priority": "Medium",
            "title": "Missing Data",
            "description": (
                "Missing values may reduce the accuracy "
                "of some analytical calculations."
            )
        })

    if duplicate_rows > 0:

        risks.append({
            "priority": "Medium",
            "title": "Duplicate Records",
            "description": (
                "Duplicate rows may influence totals, "
                "averages and other metrics."
            )
        })

    if anomalies:

        risks.append({
            "priority": "High",
            "title": "Anomalous Records",
            "description": (
                "Potential anomalies should be reviewed "
                "before making important decisions."
            )
        })

    if not risks:

        risks.append({
            "priority": "Low",
            "title": "No Major Data Risks",
            "description": (
                "No major data-quality risks were identified "
                "from the current analysis."
            )
        })

    # --------------------------------------------------------
    # OPPORTUNITIES
    # --------------------------------------------------------

    opportunities_list = []

    if numeric_columns:

        opportunities_list.append({
            "priority": "Medium",
            "title": "Performance Monitoring",
            "description": (
                "Use the available numeric metrics to "
                "track business performance over time."
            )
        })

        opportunities += 1

    if categorical_columns:

        opportunities_list.append({
            "priority": "Medium",
            "title": "Category Segmentation",
            "description": (
                "Category-level analysis can help identify "
                "high-volume and low-volume segments."
            )
        })

        opportunities += 1

    if strong_relationships > 0:

        opportunities_list.append({
            "priority": "High",
            "title": "Relationship Analysis",
            "description": (
                "Strong relationships between metrics can "
                "support deeper business investigation."
            )
        })

        opportunities += 1

    if trend_insights and trend_insights[0].get(
        "direction"
    ) != "Unavailable":

        opportunities_list.append({
            "priority": "Medium",
            "title": "Trend Monitoring",
            "description": (
                "Historical trends can be used to monitor "
                "changes in key business metrics."
            )
        })

        opportunities += 1

    # --------------------------------------------------------
    # RECOMMENDATIONS
    # --------------------------------------------------------

    recommendations = []

    if missing_cells > 0:

        recommendations.append(
            "Review and handle missing values "
            "before critical analysis."
        )

    if duplicate_rows > 0:

        recommendations.append(
            "Review duplicate records and remove "
            "duplicates where appropriate."
        )

    if strong_relationships > 0:

        recommendations.append(
            "Investigate strong relationships between "
            "numeric metrics to understand possible "
            "business drivers."
        )

    if categorical_columns:

        recommendations.append(
            "Compare major categories to identify "
            "high-performing and low-performing segments."
        )

    if numeric_columns:

        recommendations.append(
            "Monitor key numeric metrics regularly "
            "to identify meaningful changes."
        )

    if anomalies:

        recommendations.append(
            "Review anomalous records separately before "
            "using the dataset for major decisions."
        )

    if not recommendations:

        recommendations.append(
            "Continue monitoring the dataset and update "
            "the analysis as new data becomes available."
        )

    # --------------------------------------------------------
    # FINAL EXECUTIVE SUMMARY
    # --------------------------------------------------------

    executive_summary = " ".join(
        executive_points
    )

    return {
        "status": "success",

        "overview": {
            "data_quality_score": data_quality_score,
            "total_insights": total_insights,
            "critical_issues": critical_issues,
            "opportunities": opportunities,
            "strong_relationships": strong_relationships,
            "rows": rows,
            "columns": columns
        },

        "executive_summary": executive_summary,

        "key_insights": key_insights,

        "performance_insights": performance_insights,

        "category_insights": category_insights,

        "trend_insights": trend_insights,

        "correlation_insights": correlation_insights,

        "anomaly_insights": anomaly_insights,

        "data_quality_insights": data_quality_insights,

        "risks": risks,

        "opportunities": opportunities_list,

        "recommendations": recommendations
    }


@app.post("/insights")
def generate_insights(data: dict):
    if not data or not isinstance(data, dict):
        return {"status": "success", "insights": []}

    quality = data.get("data_quality_score", 0)
    quality_status = (
        "Excellent" if quality >= 90
        else "Good" if quality >= 70
        else "Needs Improvement"
    )
    strong_correlations = data.get("strong_correlations", [])
    numeric_statistics = data.get("numeric_statistics", {})
    missing_values = data.get("missing_values", {})
    missing_columns = [column for column, value in missing_values.items() if value > 0]

    insights = [
        f"Overall data quality is {quality_status} with a score of {quality}%.",
    ]

    if strong_correlations:
        strongest_relationship = max(
            strong_correlations,
            key=lambda item: abs(item.get("correlation", 0))
        )
        insights.append(
            f"{strongest_relationship.get('column1', 'A metric pair')} and "
            f"{strongest_relationship.get('column2', 'another metric')} have the strongest "
            f"association with a correlation of {strongest_relationship.get('correlation', 0)}."
        )
    else:
        insights.append("No strong relationships were detected between numeric variables.")

    if numeric_statistics:
        highest_average_column = max(
            numeric_statistics,
            key=lambda column: numeric_statistics[column].get("average", 0)
        )
        insights.append(
            f"{highest_average_column} has the highest average value among the numeric columns "
            f"({numeric_statistics[highest_average_column].get('average', 0)})."
        )

    if missing_columns:
        insights.append(
            f"{len(missing_columns)} columns contain missing values and may require data cleaning."
        )
    else:
        insights.append("No missing values were detected in the dataset.")

    return {"status": "success", "insights": insights}


@app.post("/metrics")
def generate_metrics(data: dict):
    metrics = {}

    quality = data.get("data_quality_score", 0)
    metrics["data_quality"] = quality

    numeric_statistics = data.get("numeric_statistics", {})
    if numeric_statistics:
        highest_average_column = max(
            numeric_statistics,
            key=lambda column: numeric_statistics[column]["average"]
        )

        lowest_average_column = min(
            numeric_statistics,
            key=lambda column: numeric_statistics[column]["average"]
        )

        metrics["highest_average"] = {
            "column": highest_average_column,
            "value": numeric_statistics[highest_average_column]["average"]
        }

        metrics["lowest_average"] = {
            "column": lowest_average_column,
            "value": numeric_statistics[lowest_average_column]["average"]
        }

    strong_correlations = data.get("strong_correlations", [])
    if strong_correlations:
        strongest_relationship = max(
            strong_correlations,
            key=lambda item: abs(item["correlation"])
        )

        metrics["strongest_relationship"] = {
            "column_1": strongest_relationship["column_1"],
            "column_2": strongest_relationship["column_2"],
            "correlation": strongest_relationship["correlation"]
        }

    return {
        "status": "success",
        "metrics": metrics
    }

@app.post("/summary")
def generate_summary(data: dict):
    summary = []

    numeric_statistics = data.get("numeric_statistics", {})
    if numeric_statistics:
        highest_average_column = max(
            numeric_statistics,
            key=lambda column: numeric_statistics[column]["average"]
        )
        lowest_average_column = min(
            numeric_statistics,
            key=lambda column: numeric_statistics[column]["average"]
        )
        summary.append(
            f"{highest_average_column} has the highest average value, "
            f"while {lowest_average_column} has the lowest average value."
        )

    missing_values = data.get("missing_values", {})
    missing_columns = [column for column, value in missing_values.items() if value > 0]
    if missing_columns:
        summary.append(
            f"{len(missing_columns)} columns contain missing values and may need cleaning."
        )
    else:
        summary.append("No missing values were detected in the dataset.")

    strong_correlations = data.get("strong_correlations", [])
    if strong_correlations:
        strongest_relationship = max(
            strong_correlations,
            key=lambda item: abs(item["correlation"])
        )
        summary.append(
            f"The strongest relationship is between "
            f"{strongest_relationship['column_1']} and "
            f"{strongest_relationship['column_2']} with a correlation of "
            f"{strongest_relationship['correlation']}."
        )
    else:
        summary.append("No strong relationships were detected between numeric variables.")

    return {"status": "success", "summary": summary}

@app.post("/recommendations")
def generate_recommendations(data: dict):
    recommendations = []
    quality = data.get("data_quality_score", 0)
    if quality < 90:
        recommendations.append(
            "Improve data quality by cleaning missing or inconsistent values "
            "before making important business decisions."
        )

    missing_values = data.get("missing_values", {})
    missing_columns = [
        column
        for column, value in missing_values.items()
        if value > 0
    ]

    if missing_columns:
        recommendations.append(
            f"Review and clean missing values in {len(missing_columns)} columns "
            "to improve the reliability of the analysis."
        )

    strong_correlations = data.get("strong_correlations", [])
    if strong_correlations:
        recommendations.append(
            "Investigate the strongest relationships between numeric variables "
            "to identify useful business patterns and dependencies."
        )

    numeric_statistics = data.get("numeric_statistics", {})
    if numeric_statistics:
        recommendations.append(
            "Compare the numeric metrics with the highest and lowest averages "
            "to identify areas that may need business attention."
        )

    categorical_statistics = data.get("categorical_statistics", {})
    if categorical_statistics:
        recommendations.append(
            "Review the most frequent categories to understand dominant "
            "customer, product, or business segments."
        )

    return {
        "status": "success",
        "recommendations": recommendations
    }
@app.post("/data-quality-recommendations")
def data_quality_recommendations(data: dict):
    recommendations = []

    quality = data.get("data_quality_score", 0)
    missing_values = data.get("missing_values", {})

    missing_columns = [
        column
        for column, value in missing_values.items()
        if value > 0
    ]

    if quality >= 90:
        recommendations.append(
            "Data quality is excellent. Continue regular data validation."
        )
    elif quality >= 70:
        recommendations.append(
            "Data quality is good, but some cleaning and validation may improve reliability."
        )
    else:
        recommendations.append(
            "Data quality needs improvement. Clean and validate the dataset before business analysis."
        )

    if missing_columns:
        recommendations.append(
            f"Review missing values in {len(missing_columns)} columns."
        )
    else:
        recommendations.append(
            "No missing values were detected. Continue monitoring data completeness."
        )

    return {
        "status": "success",
        "recommendations": recommendations
    }



@app.get("/data-cleaning")
def get_data_cleaning(
    current_user: str = Depends(get_current_user)
):
    user_data = user_datasets.get(current_user)

    if not user_data:
        raise HTTPException(status_code=400, detail="Please upload a dataset first.")

    df = user_data.get("df")
    if df is None or df.empty:
        raise HTTPException(status_code=400, detail="Please upload a dataset first.")

    try:
        plan = _build_cleaning_plan(df)
        return {
            "status": "success",
            "summary": plan["summary"],
            "issues": plan["issues"],
            "recommendations": plan["recommendations"],
            "cleaning_actions": plan["cleaning_actions"],
        }
    except Exception as error:
        print("Data cleaning analysis error:", error)
        raise HTTPException(status_code=500, detail="Unable to analyze the dataset for cleaning recommendations.") from error


@app.post("/data-cleaning/apply")
def apply_data_cleaning(
    payload: DataCleaningApplyRequest,
    current_user: str = Depends(get_current_user)
):
    user_data = user_datasets.get(current_user)

    if not user_data:
        raise HTTPException(status_code=400, detail="Please upload a dataset first.")

    if not payload.actions:
        raise HTTPException(status_code=400, detail="Please select at least one cleaning action.")

    df = user_data["df"].copy()
    before_rows = int(len(df))
    before_missing = int(df.isna().sum().sum())
    before_duplicates = int(df.duplicated().sum())
    before_quality = _calculate_data_quality_score(df)

    selected_actions = set(payload.actions)
    clean_df = df.copy()
    changes = []

    try:
        if "remove_duplicates" in selected_actions:
            before_size = len(clean_df)
            clean_df = clean_df.drop_duplicates().reset_index(drop=True)
            changes.append({"action": "remove_duplicates", "rows_removed": before_size - len(clean_df)})

        if "trim_text" in selected_actions:
            object_columns = clean_df.select_dtypes(exclude=[np.number]).columns.tolist()
            for column in object_columns:
                clean_df[column] = clean_df[column].astype(str).str.strip()
                clean_df[column] = clean_df[column].replace({"nan": np.nan, "None": np.nan, "": np.nan})
            changes.append({"action": "trim_text", "columns": object_columns})

        if "replace_infinite" in selected_actions:
            for column in clean_df.select_dtypes(include=[np.number]).columns:
                clean_df[column] = pd.to_numeric(clean_df[column], errors="coerce")
                clean_df[column] = clean_df[column].replace([np.inf, -np.inf], np.nan)
            changes.append({"action": "replace_infinite", "columns": clean_df.select_dtypes(include=[np.number]).columns.tolist()})

        if "fill_numeric_missing" in selected_actions:
            for column in clean_df.select_dtypes(include=[np.number]).columns:
                median_value = clean_df[column].median()
                if pd.notna(median_value):
                    clean_df[column] = clean_df[column].fillna(median_value)
            changes.append({"action": "fill_numeric_missing", "columns": clean_df.select_dtypes(include=[np.number]).columns.tolist()})

        if "fill_categorical_missing" in selected_actions:
            for column in clean_df.select_dtypes(exclude=[np.number]).columns:
                mode_value = clean_df[column].mode(dropna=True)
                if not mode_value.empty:
                    clean_df[column] = clean_df[column].fillna(mode_value.iloc[0])
                else:
                    clean_df[column] = clean_df[column].fillna("Unknown")
            changes.append({"action": "fill_categorical_missing", "columns": clean_df.select_dtypes(exclude=[np.number]).columns.tolist()})

        if "normalize_categories" in selected_actions:
            for column in clean_df.select_dtypes(exclude=[np.number]).columns:
                clean_df[column] = clean_df[column].astype(str).str.strip().str.lower()
            changes.append({"action": "normalize_categories", "columns": clean_df.select_dtypes(exclude=[np.number]).columns.tolist()})

        if "trim_text" in selected_actions and "normalize_categories" in selected_actions:
            for column in clean_df.select_dtypes(exclude=[np.number]).columns:
                clean_df[column] = clean_df[column].replace({"nan": np.nan, "none": "Unknown"})

        after_rows = int(len(clean_df))
        after_missing = int(clean_df.isna().sum().sum())
        after_duplicates = int(clean_df.duplicated().sum())
        after_quality = _calculate_data_quality_score(clean_df)

        values_changed = int((clean_df.fillna("__missing__") != df.fillna("__missing__")).sum().sum())
        if before_rows != after_rows:
            values_changed += abs(before_rows - after_rows)

        user_datasets[current_user]["df"] = clean_df.copy()
        user_datasets[current_user]["anomalies"] = []

        numeric_columns = clean_df.select_dtypes(include=[np.number]).columns.tolist()
        anomalies = []
        for column in numeric_columns:
            series = clean_df[column].dropna()
            if len(series) < 4:
                continue
            q1 = series.quantile(0.25)
            q3 = series.quantile(0.75)
            iqr = q3 - q1
            if iqr == 0:
                continue
            lower_bound = q1 - 1.5 * iqr
            upper_bound = q3 + 1.5 * iqr
            anomaly_count = int(((series < lower_bound) | (series > upper_bound)).sum())
            if anomaly_count > 0:
                anomalies.append({
                    "column": column,
                    "count": anomaly_count,
                    "lower_bound": round(float(lower_bound), 2),
                    "upper_bound": round(float(upper_bound), 2),
                })
        user_datasets[current_user]["anomalies"] = anomalies

        return {
            "status": "success",
            "message": "Selected cleaning actions applied successfully.",
            "before": {
                "rows": before_rows,
                "columns": int(df.shape[1]),
                "missing_values": before_missing,
                "duplicates": before_duplicates,
                "data_quality_score": before_quality,
            },
            "after": {
                "rows": after_rows,
                "columns": int(clean_df.shape[1]),
                "missing_values": after_missing,
                "duplicates": after_duplicates,
                "data_quality_score": after_quality,
            },
            "changes": changes,
            "rows_affected": max(0, before_rows - after_rows),
            "values_changed": values_changed,
        }
    except Exception as error:
        print("Apply cleaning error:", error)
        raise HTTPException(status_code=500, detail="Unable to apply the selected data-cleaning actions.") from error


@app.get("/forecast-columns")
def forecast_columns(
    current_user: str = Depends(get_current_user)
):

    user_data = user_datasets.get(current_user)

    if not user_data:
        raise HTTPException(
            status_code=400,
            detail="Please upload a dataset first."
        )

    df = user_data["df"]

    numeric_columns = (
        df
        .select_dtypes(include="number")
        .columns
        .tolist()
    )

    return {
        "columns": numeric_columns
    }


@app.get("/data-profile")
def get_data_profile(
    current_user: str = Depends(get_current_user)
):
    user_data = user_datasets.get(current_user)

    if not user_data:
        raise HTTPException(
            status_code=400,
            detail="Please upload a dataset first."
        )

    try:
        df = user_data["df"]
        rows, column_count = df.shape
        numeric_columns = df.select_dtypes(
            include=np.number
        ).columns.tolist()
        categorical_columns = df.select_dtypes(
            exclude=np.number
        ).columns.tolist()
        missing_values = {
            column: int(df[column].isna().sum())
            for column in df.columns
        }
        duplicate_rows = int(df.duplicated().sum())
        total_cells = rows * column_count
        missing_cells = int(df.isna().sum().sum())
        data_quality_score = (
            round(((total_cells - missing_cells) / total_cells) * 100, 2)
            if total_cells
            else 0
        )

        column_profile = []
        for column in df.columns:
            series = df[column]
            profile = {
                "name": str(column),
                "data_type": str(series.dtype),
                "missing": int(series.isna().sum()),
                "unique": int(series.nunique(dropna=True)),
            }

            if pd.api.types.is_numeric_dtype(series):
                values = series.dropna()
                finite_values = values[np.isfinite(values)]
                profile.update({
                    "min": float(finite_values.min()) if not finite_values.empty else None,
                    "max": float(finite_values.max()) if not finite_values.empty else None,
                    "average": float(finite_values.mean()) if not finite_values.empty else None,
                    "median": float(finite_values.median()) if not finite_values.empty else None,
                })
            else:
                value_counts = (
                    series.dropna().astype(str).value_counts().head(5)
                )
                profile.update({
                    "top_values": [
                        {"value": value, "count": int(count)}
                        for value, count in value_counts.items()
                    ],
                    "min": None,
                    "max": None,
                    "average": None,
                    "median": None,
                })

            column_profile.append(profile)

        correlations = []
        if len(numeric_columns) >= 2:
            correlation_matrix = df[numeric_columns].corr()
            for index, column1 in enumerate(numeric_columns):
                for column2 in numeric_columns[index + 1:]:
                    value = correlation_matrix.loc[column1, column2]
                    if pd.notna(value) and np.isfinite(value):
                        correlations.append({
                            "column1": str(column1),
                            "column2": str(column2),
                            "correlation": round(float(value), 3),
                        })

        correlations.sort(
            key=lambda item: abs(item["correlation"]),
            reverse=True
        )
        strong_correlations = [
            item for item in correlations
            if abs(item["correlation"]) >= 0.7
        ]

        insights = []
        if data_quality_score >= 90:
            insights.append("Dataset has excellent overall data quality.")
        elif data_quality_score >= 70:
            insights.append(
                "Dataset has moderate data quality and may need some cleaning."
            )
        else:
            insights.append(
                "Dataset requires data cleaning because of missing values."
            )

        insights.append(
            f"{duplicate_rows} duplicate rows were detected."
            if duplicate_rows
            else "No duplicate rows were detected."
        )
        if numeric_columns:
            insights.append(
                f"{len(numeric_columns)} numeric columns were detected."
            )
        if categorical_columns:
            insights.append(
                f"{len(categorical_columns)} categorical columns were detected."
            )

        return {
            "status": "success",
            "overview": {
                "rows": rows,
                "columns": column_count,
                "numeric_columns": len(numeric_columns),
                "categorical_columns": len(categorical_columns),
                "duplicate_rows": duplicate_rows,
                "data_quality_score": data_quality_score,
            },
            "numeric_columns": [str(column) for column in numeric_columns],
            "categorical_columns": [str(column) for column in categorical_columns],
            "missing_values": {
                str(column): count
                for column, count in missing_values.items()
            },
            "column_profile": column_profile,
            "correlations": correlations[:20],
            "strong_correlations": strong_correlations[:10],
            "insights": insights,
        }
    except Exception as error:
        print("Data profile error:", error)
        raise HTTPException(
            status_code=500,
            detail="Unable to generate data profile."
        ) from error


@app.get("/what-if/columns")
def what_if_columns(
    current_user: str = Depends(get_current_user)
):
    user_data = user_datasets.get(current_user)

    if not user_data:
        raise HTTPException(status_code=400, detail="Please upload a dataset first.")

    df = user_data["df"]
    columns = [str(column) for column in df.select_dtypes(include=[np.number]).columns.tolist()]
    return {
        "status": "success",
        "columns": columns,
    }


@app.post("/what-if")
def what_if_analysis(
    payload: WhatIfRequest,
    current_user: str = Depends(get_current_user)
):
    user_data = user_datasets.get(current_user)

    if not user_data:
        raise HTTPException(status_code=400, detail="Please upload a dataset first.")

    df = user_data["df"]
    if payload.column not in df.columns:
        raise HTTPException(status_code=400, detail="Selected metric was not found in the uploaded dataset.")

    if not pd.api.types.is_numeric_dtype(df[payload.column]):
        raise HTTPException(status_code=400, detail="Please select a numeric column for scenario analysis.")

    series = pd.to_numeric(df[payload.column], errors="coerce").dropna()
    if series.empty:
        raise HTTPException(status_code=400, detail="The selected metric has no usable numeric values for simulation.")

    original_value = float(series.sum())

    scenario_type = payload.scenario_type.lower()
    if scenario_type in {"increase_by_percent", "decrease_by_percent"}:
        if payload.change_percent is None:
            raise HTTPException(status_code=400, detail="A percentage change value is required for this scenario.")
        ratio = 1 + (payload.change_percent / 100) if scenario_type == "increase_by_percent" else 1 - (payload.change_percent / 100)
        scenario_value = original_value * ratio
        absolute_change = scenario_value - original_value
        percentage_change = (absolute_change / original_value) * 100 if original_value else 0
    elif scenario_type == "change_by_value":
        if payload.change_value is None:
            raise HTTPException(status_code=400, detail="A change value is required for this scenario.")
        scenario_value = original_value + payload.change_value
        absolute_change = scenario_value - original_value
        percentage_change = (absolute_change / original_value) * 100 if original_value else 0
    else:
        raise HTTPException(status_code=400, detail="Unsupported scenario type.")

    if original_value >= 0 and scenario_value < 0:
        raise HTTPException(status_code=400, detail="The resulting scenario value cannot be negative for this metric.")

    kpi_impact = []
    target_lower = str(payload.column).lower()
    related_candidates = []
    for candidate in df.select_dtypes(include=[np.number]).columns:
        candidate_name = str(candidate).lower()
        if candidate == payload.column:
            continue
        if any(keyword in target_lower for keyword in ["sales", "revenue", "profit", "quantity", "price"]) and any(keyword in candidate_name for keyword in ["sales", "revenue", "profit", "quantity", "price", "margin", "cost"]):
            related_candidates.append(str(candidate))
        elif any(keyword in candidate_name for keyword in ["sales", "revenue", "profit", "quantity", "price"]) and any(keyword in target_lower for keyword in ["sales", "revenue", "profit", "quantity", "price", "margin", "cost"]):
            related_candidates.append(str(candidate))

    if related_candidates:
        for column_name in related_candidates[:3]:
            related_series = pd.to_numeric(df[column_name], errors="coerce").dropna()
            if related_series.empty:
                continue
            related_original = float(related_series.sum())
            related_scenario = related_original * (scenario_value / original_value) if original_value else related_original
            kpi_impact.append({
                "name": column_name,
                "original_value": round(related_original, 2),
                "scenario_value": round(related_scenario, 2),
                "absolute_change": round(related_scenario - related_original, 2),
                "percentage_change": round(((related_scenario - related_original) / related_original) * 100, 2) if related_original else 0,
                "note": "Estimated using the same scenario ratio as the selected metric.",
            })

    if not kpi_impact:
        insight = (
            f"A {abs(percentage_change):.2f}% {'increase' if percentage_change >= 0 else 'decrease'} in {payload.column} would change the selected metric by approximately {abs(percentage_change):.2f}%. "
            "Other KPI impacts depend on the relationships available in the uploaded dataset."
        )
    else:
        insight = (
            f"Based on the selected scenario, {payload.column} would change by approximately {abs(percentage_change):.2f}%. "
            "The related KPI estimates below are scenario-based and should be treated as directional estimates."
        )

    response = {
        "status": "success",
        "scenario": {
            "column": payload.column,
            "scenario_type": scenario_type,
            "change_percent": payload.change_percent,
            "change_value": payload.change_value,
        },
        "results": {
            "original_value": round(original_value, 2),
            "scenario_value": round(scenario_value, 2),
            "absolute_change": round(absolute_change, 2),
            "percentage_change": round(percentage_change, 2),
        },
        "kpi_impact": kpi_impact,
        "insight": insight,
    }
    return response


@app.post("/forecast")
def forecast(
    data: ForecastRequest,
    current_user: str = Depends(get_current_user)
):

    user_data = user_datasets.get(current_user)

    if not user_data:
        raise HTTPException(
            status_code=400,
            detail="Please upload a dataset first."
        )

    df = user_data["df"]

    if data.column not in df.columns:
        raise HTTPException(
            status_code=400,
            detail="Selected column was not found."
        )

    if not pd.api.types.is_numeric_dtype(df[data.column]):
        raise HTTPException(
            status_code=400,
            detail="Please select a numeric column."
        )

    numeric_series = pd.to_numeric(df[data.column], errors="coerce")
    series = numeric_series.replace([np.inf, -np.inf], np.nan).dropna()
    excluded_values = int(len(numeric_series) - len(series))

    if len(series) < 3:
        raise HTTPException(
            status_code=400,
            detail="At least 3 valid numeric values are required for forecasting."
        )

    y = series.to_numpy(dtype=float)

    smoothing_level = 0.8
    smoothing_trend = 0.2
    damping = 0.9
    level = y[0]
    trend_estimate = y[1] - y[0]

    for value in y[1:]:
        previous_level = level
        level = (
            smoothing_level * value
            + (1 - smoothing_level) * (previous_level + damping * trend_estimate)
        )
        trend_estimate = (
            smoothing_trend * (level - previous_level)
            + (1 - smoothing_trend) * damping * trend_estimate
        )

    predictions = np.array([
        level + trend_estimate * sum(
            damping ** step for step in range(1, period + 1)
        )
        for period in range(1, data.periods + 1)
    ])

    if not np.isfinite(predictions).all():
        raise HTTPException(
            status_code=422,
            detail="The forecast produced non-finite values for this series.",
        )

    historical = [
        {
            "period": index + 1,
            "value": round(float(value), 2)
        }
        for index, value in enumerate(y)
    ]

    forecast_values = [
        {
            "period": len(series) + index + 1,
            "value": round(float(value), 2)
        }
        for index, value in enumerate(predictions)
    ]
    trend = float(predictions[-1] - y[-1])
    direction = (
        "increasing" if trend > 1e-8
        else "decreasing" if trend < -1e-8
        else "stable"
    )
    outlook = (
        "continued growth" if direction == "increasing"
        else "a continued decline" if direction == "decreasing"
        else "continued stability"
    )

    return {
        "status": "success",
        "column": data.column,
        "historical": historical,
        "forecast": forecast_values,
        "trend": round(trend, 4),
        "trend_direction": direction,
        "insight": (
            f"The selected metric shows an {direction} trend. "
            f"The forecast indicates {outlook} over the next {data.periods} periods."
        ),
        "excluded_values": excluded_values,
    }


@app.get("/report")
def generate_report(
    current_user: str = Depends(get_current_user)
):

    user_data = user_datasets.get(current_user)

    if not user_data:
        raise HTTPException(
            status_code=400,
            detail="Please upload a dataset first."
        )

    df = user_data["df"]
    anomalies = user_data["anomalies"]

    numeric_columns = (
        df.select_dtypes(include="number")
        .columns
        .tolist()
    )

    categorical_columns = (
        df.select_dtypes(exclude="number")
        .columns
        .tolist()
    )

    missing_values = {
        column: int(value)
        for column, value in df.isnull().sum().items()
        if value > 0
    }

    numeric_statistics = {}

    for column in numeric_columns:
        series = pd.to_numeric(
            df[column],
            errors="coerce"
        ).dropna()

        if len(series) > 0:
            numeric_statistics[column] = {
                "average": round(float(series.mean()), 2),
                "median": round(float(series.median()), 2),
                "minimum": round(float(series.min()), 2),
                "maximum": round(float(series.max()), 2)
            }

    return {
        "status": "success",
        "rows": int(df.shape[0]),
        "columns": int(df.shape[1]),
        "numeric_columns": numeric_columns,
        "categorical_columns": categorical_columns,
        "missing_values": missing_values,
        "numeric_statistics": numeric_statistics,
        "anomalies": anomalies
    }


def add_pdf_footer(canvas, doc):
    canvas.saveState()

    # Top Header
    canvas.setFont("Helvetica-Bold", 9)

    canvas.drawString(
        40,
        A4[1] - 25,
        "AI Business Analyst"
    )

    # Bottom Footer
    canvas.setFont("Helvetica", 9)

    canvas.drawString(
        40,
        25,
        "AI Business Analyst | Confidential Report"
    )

    canvas.drawRightString(
        A4[0] - 40,
        25,
        "Page " + str(doc.page)
    )

    canvas.restoreState()


@app.get("/report/pdf")
def generate_pdf_report(
    current_user: str = Depends(get_current_user)
):

    user_data = user_datasets.get(current_user)

    if not user_data:
        raise HTTPException(
            status_code=400,
            detail="Please upload a dataset first."
        )

    uploaded_df = user_data["df"]
    uploaded_anomalies = user_data["anomalies"]

    rows = len(uploaded_df)
    columns = len(uploaded_df.columns)
    numeric_columns = uploaded_df.select_dtypes(include=np.number).columns.tolist()
    categorical_columns = uploaded_df.select_dtypes(exclude=np.number).columns.tolist()

    missing_values = {
        column: int(uploaded_df[column].isnull().sum())
        for column in uploaded_df.columns
        if uploaded_df[column].isnull().sum() > 0
    }

    numeric_statistics = {}
    for column in numeric_columns:
        series = pd.to_numeric(uploaded_df[column], errors="coerce").dropna()
        if len(series) > 0:
            numeric_statistics[column] = {
                "average": round(float(series.mean()), 2),
                "median": round(float(series.median()), 2),
                "minimum": round(float(series.min()), 2),
                "maximum": round(float(series.max()), 2),
            }

    anomalies = uploaded_anomalies
    pdf_path = os.path.join(tempfile.gettempdir(), "AI_Business_Analyst_Report.pdf")

    doc = SimpleDocTemplate(
        pdf_path,
        pagesize=A4,
        rightMargin=40,
        leftMargin=40,
        topMargin=40,
        bottomMargin=40,
    )

    styles = getSampleStyleSheet()
    heading_style = styles["Heading2"]
    heading_style.fontSize = 15
    heading_style.leading = 20
    heading_style.spaceBefore = 12
    heading_style.spaceAfter = 8
    normal_style = styles["BodyText"]
    normal_style.fontSize = 10
    normal_style.leading = 15
    normal_style.spaceAfter = 6

    story = []
    generated_date = datetime.now().strftime("%d %B %Y, %I:%M %p")

    story.append(Paragraph(f"Generated on: {generated_date}", normal_style))
    story.append(Spacer(1, 10))

    report_title_style = styles["Title"]
    report_title_style.fontSize = 24
    report_title_style.leading = 30
    report_title_style.alignment = 1
    report_title_style.spaceAfter = 8

    report_subtitle_style = styles["BodyText"]
    report_subtitle_style.fontSize = 11
    report_subtitle_style.alignment = 1
    report_subtitle_style.spaceAfter = 6

    story.append(Paragraph("AI BUSINESS ANALYST", report_title_style))
    story.append(Paragraph("Professional Business Intelligence Report", report_subtitle_style))
    story.append(Paragraph("Automated Data Analysis & Business Intelligence", report_subtitle_style))
    story.append(Spacer(1, 25))

    total_cells = rows * columns
    if total_cells > 0:
        missing_cells = int(uploaded_df.isnull().sum().sum())
        data_quality_score = round(((total_cells - missing_cells) / total_cells) * 100, 2)
    else:
        data_quality_score = 0

    story.append(Paragraph("Executive Summary", heading_style))
    executive_summary = (
        f"This report provides an automated analysis of the uploaded dataset. "
        f"The dataset contains {rows} rows and {columns} columns, with "
        f"{len(numeric_columns)} numeric and {len(categorical_columns)} categorical columns. "
        f"The overall data quality score is {data_quality_score}%. "
    )
    if anomalies:
        executive_summary += (
            f"Potential unusual values were detected in {len(anomalies)} column(s) and may require further review."
        )
    else:
        executive_summary += "No potential unusual values were detected."
    story.append(Paragraph(executive_summary, normal_style))
    story.append(Spacer(1, 20))

    story.append(Paragraph("Dataset Summary", heading_style))
    summary_data = [
        ["Metric", "Value"],
        ["Total Rows", str(rows)],
        ["Total Columns", str(columns)],
        ["Data Quality Score", f"{data_quality_score}%"],
        ["Numeric Columns", str(len(numeric_columns))],
        ["Categorical Columns", str(len(categorical_columns))],
        ["Anomaly Columns", str(len(anomalies))],
    ]
    summary_table = Table(summary_data, colWidths=[250, 150])
    summary_table.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#111827")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTNAME", (0, 1), (0, -1), "Helvetica-Bold"),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#D1D5DB")),
            ("BACKGROUND", (0, 1), (-1, -1), colors.HexColor("#F9FAFB")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F9FAFB")]),
            ("ALIGN", (1, 1), (-1, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("PADDING", (0, 0), (-1, -1), 8),
        ])
    )
    story.append(summary_table)
    story.append(Spacer(1, 20))

    story.append(Paragraph("Numeric Statistics", heading_style))
    if numeric_statistics:
        statistics_data = [["Column", "Average", "Median", "Minimum", "Maximum"]]
        for column, stats in numeric_statistics.items():
            statistics_data.append([
                column,
                str(stats["average"]),
                str(stats["median"]),
                str(stats["minimum"]),
                str(stats["maximum"]),
            ])
        statistics_table = Table(statistics_data, repeatRows=1)
        statistics_table.setStyle(
            TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#111827")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTNAME", (0, 1), (0, -1), "Helvetica-Bold"),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#D1D5DB")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F9FAFB")]),
                ("ALIGN", (1, 1), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("PADDING", (0, 0), (-1, -1), 7),
            ])
        )
        story.append(statistics_table)
    else:
        story.append(Paragraph("No numeric columns detected.", normal_style))

    story.append(Spacer(1, 20))
    story.append(Paragraph("Missing Values", heading_style))
    if missing_values:
        missing_data = [["Column", "Missing Values"]]
        missing_data.extend([column, str(value)] for column, value in missing_values.items())
        missing_table = Table(missing_data, colWidths=[300, 120], repeatRows=1)
        missing_table.setStyle(
            TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#111827")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#D1D5DB")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F9FAFB")]),
                ("ALIGN", (1, 1), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("PADDING", (0, 0), (-1, -1), 7),
            ])
        )
        story.append(missing_table)
    else:
        story.append(Paragraph("No missing values detected.", normal_style))

    story.append(Spacer(1, 20))
    story.append(
        Paragraph(
            "Correlation Analysis shows how strongly two numeric columns are related. Values closer to +1 indicate a strong positive relationship, while values closer to -1 indicate a strong negative relationship.",
            normal_style,
        )
    )
    story.append(Spacer(1, 10))

    story.append(Paragraph("Correlation Analysis", heading_style))
    correlations = uploaded_df.corr(numeric_only=True)
    strong_correlations = []
    for column1 in correlations.columns:
        for column2 in correlations.columns:
            if column1 < column2:
                value = correlations.loc[column1, column2]
                if abs(value) >= 0.7:
                    strong_correlations.append([column1, column2, round(float(value), 2)])

    if strong_correlations:
        correlation_data = [["Column 1", "Column 2", "Correlation"]]
        correlation_data.extend(strong_correlations)
        correlation_table = Table(correlation_data, colWidths=[170, 170, 100], repeatRows=1)
        correlation_table.setStyle(
            TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#111827")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#D1D5DB")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F9FAFB")]),
                ("ALIGN", (2, 1), (-1, -1), "CENTER"),
                ("PADDING", (0, 0), (-1, -1), 7),
            ])
        )
        story.append(correlation_table)
    else:
        story.append(Paragraph("No strong correlations detected.", normal_style))

    story.append(Spacer(1, 20))
    story.append(Paragraph("Business Insights", heading_style))

    insights = []
    if numeric_statistics:
        highest_column = max(numeric_statistics, key=lambda x: numeric_statistics[x]["average"])
        lowest_column = min(numeric_statistics, key=lambda x: numeric_statistics[x]["average"])
        insights.append(f"Highest average value: {highest_column}")
        insights.append(f"Lowest average value: {lowest_column}")

    if data_quality_score >= 90:
        insights.append("The dataset has a high overall data quality score.")
    elif data_quality_score >= 70:
        insights.append("The dataset has moderate data quality and may require some cleaning.")
    else:
        insights.append("The dataset may require significant data cleaning.")

    if strong_correlations:
        insights.append("Strong relationships were identified between some numeric columns.")
    else:
        insights.append("No strong relationships were identified between numeric columns.")

    if anomalies:
        insights.append("Potential unusual values were detected and should be reviewed.")
    else:
        insights.append("No unusual values were detected.")

    for insight in insights:
        story.append(Paragraph("• " + insight, normal_style))

    story.append(Spacer(1, 20))
    story.append(Paragraph("Report Conclusion", heading_style))
    conclusion_text = (
        f"The analysis was performed on a dataset containing {rows} rows and {columns} columns. "
        f"The overall data quality score is {data_quality_score}%. "
    )
    if anomalies:
        conclusion_text += "Potential anomalies were identified and should be reviewed before making important business decisions."
    else:
        conclusion_text += "No significant anomalies were detected in the dataset."
    story.append(Paragraph(conclusion_text, normal_style))
    story.append(Spacer(1, 20))

    story.append(Paragraph("Anomaly Detection", heading_style))
    if anomalies:
        anomaly_data = [["Column", "Unusual Values"]]
        anomaly_data.extend([[item["column"], str(item["count"])] for item in anomalies])
        anomaly_table = Table(anomaly_data, colWidths=[300, 120], repeatRows=1)
        anomaly_table.setStyle(
            TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#111827")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#D1D5DB")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F9FAFB")]),
                ("ALIGN", (1, 1), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("PADDING", (0, 0), (-1, -1), 7),
            ])
        )
        story.append(anomaly_table)
    else:
        story.append(Paragraph("No anomalies detected.", normal_style))

    doc.build(story, onFirstPage=add_pdf_footer, onLaterPages=add_pdf_footer)

    return FileResponse(
        pdf_path,
        media_type="application/pdf",
        filename="AI_Business_Analyst_Report.pdf",
    )


@app.post("/upload")
async def upload_dataset(
    file: UploadFile = File(...),
    current_user: str = Depends(get_current_user)
):

    allowed_extensions = [".csv", ".xlsx", ".xls"]

    filename = file.filename or ""

    if not filename:
        raise HTTPException(
            status_code=400,
            detail="Please select a file."
        )

    filename = filename.lower()

    if not any(filename.endswith(ext) for ext in allowed_extensions):
        raise HTTPException(
            status_code=400,
            detail="Only CSV and Excel files are supported."
        )

    # Enforce the authoritative 100 MB upload limit before any pandas processing.
    file.file.seek(0, os.SEEK_END)
    file_size = file.file.tell()
    file.file.seek(0)

    if file_size > MAX_UPLOAD_SIZE_BYTES:
        raise HTTPException(
            status_code=413,
            detail="File size exceeds the maximum allowed limit of 100 MB."
        )

    try:
        # Read uploaded file
        if filename.endswith(".csv"):
            df = pd.read_csv(file.file)
        else:
            df = pd.read_excel(file.file)

        if df.empty:
            raise HTTPException(
                status_code=400,
                detail="The uploaded dataset is empty."
            )

        # Basic dataset information
        rows, columns = df.shape
        duplicate_rows = int(df.duplicated().sum())

        # Calculate missing values
        missing_values = df.isnull().sum().to_dict()

        # Calculate data quality score
        total_cells = rows * columns
        total_missing = int(df.isnull().sum().sum())

        if total_cells > 0:
            data_quality_score = round(
                ((total_cells - total_missing) / total_cells) * 100,
                2
            )
        else:
            data_quality_score = 0

        # Identify numeric and categorical columns
        numeric_columns = df.select_dtypes(include="number").columns.tolist()
        categorical_columns = df.select_dtypes(
            include=["object", "category"]
        ).columns.tolist()

        # Detect anomalies using IQR method
        anomalies = []

        for column in numeric_columns:
            series = df[column].dropna()

            if len(series) < 4:
                continue

            Q1 = series.quantile(0.25)
            Q3 = series.quantile(0.75)
            IQR = Q3 - Q1

            if IQR == 0:
                continue

            lower_bound = Q1 - 1.5 * IQR
            upper_bound = Q3 + 1.5 * IQR

            anomaly_count = int(
                ((series < lower_bound) | (series > upper_bound)).sum()
            )

            if anomaly_count > 0:
                anomalies.append({
                    "column": column,
                    "count": anomaly_count,
                    "lower_bound": round(float(lower_bound), 2),
                    "upper_bound": round(float(upper_bound), 2)
                })

        user_datasets[current_user] = {
            "df": df.copy(),
            "anomalies": anomalies
        }

        # Calculate statistics for numeric columns
        numeric_statistics = {}

        for column in numeric_columns:
            numeric_statistics[column] = {
                "min": float(df[column].min()),
                "max": float(df[column].max()),
                "average": round(float(df[column].mean()), 2),
                "median": float(df[column].median())
            }
        # Calculate frequency for categorical columns
        categorical_statistics = {}

        for column in categorical_columns:
            value_counts = df[column].fillna("Missing").value_counts()

            categorical_statistics[column] = {
                "unique_values": int(df[column].nunique(dropna=True)),
                "top_values": [
                    {
                        "value": str(value),
                        "count": int(count)
                    }
                    for value, count in value_counts.head(10).items()
                ]
            }

        # Calculate correlation between numeric columns
        correlation_matrix = {}
        strong_correlations = []

        if len(numeric_columns) >= 2:
            correlation_df = df[numeric_columns].corr()

            for column in numeric_columns:
                correlation_matrix[column] = {
                    other_column: round(
                        float(correlation_df.loc[column, other_column]), 3
                    )
                    for other_column in numeric_columns
                    if column != other_column
                    and pd.notna(correlation_df.loc[column, other_column])
                }

            # Identify strong correlations
            for index, column in enumerate(numeric_columns):
                for other_column in numeric_columns[index + 1:]:
                    correlation_value = correlation_df.loc[column, other_column]

                    if pd.notna(correlation_value) and abs(correlation_value) >= 0.7:
                        strong_correlations.append({
                            "column_1": column,
                            "column_2": other_column,
                            "correlation": round(float(correlation_value), 3)
                        })

        return {
            "message": "Dataset uploaded successfully",
            "filename": file.filename,
            "rows": rows,
            "columns": columns,
            "numeric_columns": numeric_columns,
            "categorical_columns": categorical_columns,
            "missing_values": missing_values,
            "data_quality_score": data_quality_score,
            "numeric_statistics": numeric_statistics,
            "categorical_statistics": categorical_statistics,
            "correlation_matrix": correlation_matrix,
            "strong_correlations": strong_correlations,
            "anomalies": anomalies,
            "column_names": df.columns.tolist(),
            "preview": df.head(5).fillna("").to_dict(orient="records")
        }

    except HTTPException:
        raise
    except pd.errors.EmptyDataError:
        raise HTTPException(
            status_code=400,
            detail="The uploaded dataset is empty."
        )
    except Exception as e:
        print("Upload processing error:", e)
        raise HTTPException(
            status_code=500,
            detail="Unable to process the dataset. Please check the file and try again."
        )


@app.post("/kpis")
async def generate_kpis(file: UploadFile = File(...)):

    try:
        filename = (file.filename or "").lower()

        if not filename:
            raise HTTPException(
                status_code=400,
                detail="Please select a file."
            )

        if filename.endswith(".csv"):
            df = pd.read_csv(file.file)

        elif filename.endswith((".xlsx", ".xls")):
            df = pd.read_excel(file.file)

        else:
            raise HTTPException(
                status_code=400,
                detail="Only CSV and Excel files are supported."
            )

        if df.empty:
            raise HTTPException(
                status_code=400,
                detail="The uploaded dataset is empty."
            )

        numeric_columns = df.select_dtypes(
            include="number"
        ).columns.tolist()

        business_columns = {
            "revenue": None,
            "sales": None,
            "profit": None,
            "quantity": None
        }

        for column in numeric_columns:
            column_name = column.lower().replace("_", " ").replace("-", " ")

            if business_columns["revenue"] is None and any(
                word in column_name
                for word in ["revenue", "income", "turnover"]
            ):
                business_columns["revenue"] = column

            if business_columns["sales"] is None and any(
                word in column_name
                for word in ["sales", "sale", "amount"]
            ):
                business_columns["sales"] = column

            if business_columns["profit"] is None and "profit" in column_name:
                business_columns["profit"] = column

            if business_columns["quantity"] is None and any(
                word in column_name
                for word in ["quantity", "qty", "units"]
            ):
                business_columns["quantity"] = column

        metrics = {}
        kpis = {}

        for column in numeric_columns:
            column_metrics = {
                "total": float(df[column].sum()),
                "average": float(df[column].mean()),
                "maximum": float(df[column].max()),
                "minimum": float(df[column].min())
            }
            metrics[column] = column_metrics

        for business_name, column in business_columns.items():
            if column is not None:
                kpis[business_name] = metrics[column]
        detected = {
        "revenue": business_columns["revenue"],
        "sales": business_columns["sales"],
        "profit": business_columns["profit"],
        "quantity": business_columns["quantity"]
}

        # Key Business Metrics

        # Data Quality Score
        total_cells = df.shape[0] * df.shape[1]

        if total_cells > 0:
            missing_cells = df.isnull().sum().sum()
            data_quality_score = round(
                ((total_cells - missing_cells) / total_cells) * 100,
                2
            )
        else:
            data_quality_score = 0

        # Highest and Lowest Average
        averages = {
            column: float(df[column].mean())
            for column in numeric_columns
            if not df[column].dropna().empty
        }

        highest_average = None
        lowest_average = None

        if averages:
            highest_column = max(averages, key=averages.get)
            lowest_column = min(averages, key=averages.get)

            highest_average = {
                "column": highest_column,
                "value": averages[highest_column]
            }

            lowest_average = {
                "column": lowest_column,
                "value": averages[lowest_column]
            }

        # Strongest Relationship
        strongest_relationship = None

        if len(numeric_columns) >= 2:
            correlation_matrix = df[numeric_columns].corr()

            strongest_pair = None
            strongest_value = 0

            for i in range(len(numeric_columns)):
                for j in range(i + 1, len(numeric_columns)):
                    value = correlation_matrix.iloc[i, j]

                    if pd.notna(value) and abs(value) > abs(strongest_value):
                        strongest_value = float(value)
                        strongest_pair = (
                            numeric_columns[i],
                            numeric_columns[j]
                        )

            if strongest_pair:
                strongest_relationship = {
                    "columns": list(strongest_pair),
                    "correlation": strongest_value
                }

        key_metrics = {
            "data_quality_score": data_quality_score,
            "highest_average": highest_average,
            "lowest_average": lowest_average,
            "strongest_relationship": strongest_relationship
        }

        summary = {
            "total_rows": int(len(df)),
            "total_columns": int(len(df.columns)),
            "numeric_columns": int(len(numeric_columns))
        }

        return {
            "message": "KPIs generated successfully",
            "summary": summary,
            "metrics": metrics,
            "business_columns": business_columns,
            "kpis": kpis,
            "detected_business_columns": detected,
            "key_metrics": key_metrics

        }

    except HTTPException:
        raise
    except pd.errors.EmptyDataError:
        raise HTTPException(
            status_code=400,
            detail="The uploaded dataset is empty."
        )
    except Exception as e:
        print("KPI generation error:", e)
        raise HTTPException(
            status_code=500,
            detail="Unable to generate KPIs. Please check the file and try again."
        )