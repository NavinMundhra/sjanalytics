"""
LLM Tools - Python wrappers for LLM function calling.

These functions bridge the LLM with our deterministic services.
The LLM calls these tools, they execute SQL queries, and return results.
"""
from sqlalchemy.orm import Session
from datetime import date, datetime
from typing import List, Dict, Any, Optional
from . import metrics_service, visualization_service
import json
import base64


def tool_get_timeseries(
    db: Session,
    site_ids: List[str],
    metric_names: List[str],
    from_date: str,  # ISO format: "2024-04-01"
    to_date: str,
    data_version: Optional[str] = None
) -> Dict[str, Any]:
    """
    Get time series data for specified sites and metrics.

    Args:
        db: Database session
        site_ids: List of site IDs (e.g., ["KIMS_NASIK", "MANIPAL_GOA"])
        metric_names: List of metric names (e.g., ["revenue", "energy_savings"])
        from_date: Start date in ISO format (YYYY-MM-DD)
        to_date: End date in ISO format
        data_version: Optional data version

    Returns:
        Dict with timeseries data
    """
    # Parse dates
    from_dt = datetime.fromisoformat(from_date).date()
    to_dt = datetime.fromisoformat(to_date).date()

    # Call service
    result = metrics_service.get_timeseries(
        db=db,
        site_ids=site_ids,
        metric_names=metric_names,
        from_date=from_dt,
        to_date=to_dt,
        data_version=data_version
    )

    # Convert to dict
    return {
        "points": [p.dict() for p in result.points],
        "total_points": result.total_points,
        "sites": result.sites,
        "metrics": result.metrics
    }


def tool_get_summary(
    db: Session,
    metric_name: str,
    from_date: str,
    to_date: str,
    site_id: Optional[str] = None,
    aggregation: str = "sum",
    data_version: Optional[str] = None
) -> Dict[str, Any]:
    """
    Get aggregated summary for a metric.

    Args:
        db: Database session
        metric_name: Metric name (e.g., "revenue")
        from_date: Start date (ISO format)
        to_date: End date (ISO format)
        site_id: Optional site ID (None for all sites)
        aggregation: "sum", "avg", "min", or "max"
        data_version: Optional data version

    Returns:
        Dict with summary data
    """
    from_dt = datetime.fromisoformat(from_date).date()
    to_dt = datetime.fromisoformat(to_date).date()

    result = metrics_service.get_summary(
        db=db,
        site_id=site_id,
        metric_name=metric_name,
        from_date=from_dt,
        to_date=to_dt,
        aggregation=aggregation,
        data_version=data_version
    )

    return result.dict()


def tool_get_ranking(
    db: Session,
    metric_name: str,
    from_date: str,
    to_date: str,
    top_n: int = 5,
    ascending: bool = False,
    data_version: Optional[str] = None
) -> Dict[str, Any]:
    """
    Get top/bottom N sites for a metric.

    Args:
        db: Database session
        metric_name: Metric to rank by
        from_date: Start date (ISO format)
        to_date: End date (ISO format)
        top_n: Number of sites to return
        ascending: True for bottom N, False for top N
        data_version: Optional data version

    Returns:
        Dict with ranked sites
    """
    from_dt = datetime.fromisoformat(from_date).date()
    to_dt = datetime.fromisoformat(to_date).date()

    results = metrics_service.get_ranking(
        db=db,
        metric_name=metric_name,
        from_date=from_dt,
        to_date=to_dt,
        top_n=top_n,
        ascending=ascending,
        data_version=data_version
    )

    return {
        "rankings": [r.dict() for r in results],
        "total": len(results),
        "metric": metric_name,
        "order": "ascending" if ascending else "descending"
    }


def tool_get_sites(db: Session, data_version: Optional[str] = None) -> List[Dict[str, str]]:
    """Get list of all available sites"""
    return metrics_service.get_site_list(db, data_version)


def tool_get_metrics(db: Session, data_version: Optional[str] = None) -> List[Dict[str, str]]:
    """Get list of all available metrics"""
    return metrics_service.get_metric_list(db, data_version)


def tool_generate_chart(
    title: str,
    chart_type: str,  # "timeseries", "bar", "comparison"
    data: Dict[str, Any],
) -> str:
    """
    Generate a chart and return as base64 PNG.

    Args:
        title: Chart title
        chart_type: Type of chart ("timeseries", "bar", "comparison")
        data: Chart data (structure depends on type)

    Returns:
        Base64 encoded PNG image
    """
    if chart_type == "timeseries":
        # Expect data = {"x": [...], "series": [...], "y_label": "..."}
        png_bytes = visualization_service.render_timeseries_chart(
            title=title,
            x=[datetime.fromisoformat(d).date() for d in data["x"]],
            series=data["series"],
            y_label=data.get("y_label", "Value")
        )
    elif chart_type == "bar":
        # Expect data = {"categories": [...], "values": [...], "y_label": "..."}
        png_bytes = visualization_service.render_bar_chart(
            title=title,
            categories=data["categories"],
            values=data["values"],
            y_label=data.get("y_label", "Value")
        )
    elif chart_type == "comparison":
        # Expect data = {"categories": [...], "series": [...], "y_label": "..."}
        png_bytes = visualization_service.render_comparison_chart(
            title=title,
            categories=data["categories"],
            series=data["series"],
            y_label=data.get("y_label", "Value")
        )
    else:
        raise ValueError(f"Unknown chart type: {chart_type}")

    # Encode as base64
    return base64.b64encode(png_bytes).decode('utf-8')


# Tool definitions for LLM (OpenAI function calling format)
TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "get_timeseries",
            "description": "Get time series data for one or more sites and metrics over a date range. Returns monthly data points.",
            "parameters": {
                "type": "object",
                "properties": {
                    "site_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of site IDs (e.g., ['KIMS_NASIK', 'MANIPAL_GOA'])"
                    },
                    "metric_names": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of metric names (e.g., ['revenue', 'energy_savings'])"
                    },
                    "from_date": {
                        "type": "string",
                        "description": "Start date in ISO format (YYYY-MM-DD)"
                    },
                    "to_date": {
                        "type": "string",
                        "description": "End date in ISO format (YYYY-MM-DD)"
                    }
                },
                "required": ["site_ids", "metric_names", "from_date", "to_date"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_summary",
            "description": "Get aggregated summary (sum/avg/min/max) for a metric over a date range. Can be for one site or all sites.",
            "parameters": {
                "type": "object",
                "properties": {
                    "metric_name": {
                        "type": "string",
                        "description": "Metric name (e.g., 'revenue')"
                    },
                    "from_date": {
                        "type": "string",
                        "description": "Start date (YYYY-MM-DD)"
                    },
                    "to_date": {
                        "type": "string",
                        "description": "End date (YYYY-MM-DD)"
                    },
                    "site_id": {
                        "type": "string",
                        "description": "Optional site ID. Omit for all sites."
                    },
                    "aggregation": {
                        "type": "string",
                        "enum": ["sum", "avg", "min", "max"],
                        "description": "Aggregation function"
                    }
                },
                "required": ["metric_name", "from_date", "to_date"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_ranking",
            "description": "Get top N or bottom N sites ranked by a metric over a date range.",
            "parameters": {
                "type": "object",
                "properties": {
                    "metric_name": {"type": "string"},
                    "from_date": {"type": "string"},
                    "to_date": {"type": "string"},
                    "top_n": {
                        "type": "integer",
                        "description": "Number of sites to return (default 5)"
                    },
                    "ascending": {
                        "type": "boolean",
                        "description": "True for bottom N, False for top N (default False)"
                    }
                },
                "required": ["metric_name", "from_date", "to_date"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_sites",
            "description": "Get list of all available site IDs and names in the database.",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_metrics",
            "description": "Get list of all available metric names and units in the database.",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "generate_chart",
            "description": "Generate a chart (timeseries, bar, or comparison) and return as base64 PNG.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "chart_type": {
                        "type": "string",
                        "enum": ["timeseries", "bar", "comparison"]
                    },
                    "data": {
                        "type": "object",
                        "description": "Chart data structure (varies by type)"
                    }
                },
                "required": ["title", "chart_type", "data"]
            }
        }
    }
]
