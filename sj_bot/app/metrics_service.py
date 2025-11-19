"""
Metrics service - deterministic data queries (NO LLM).

This module provides 100% accurate, SQL-based queries for metrics.
All calculations are deterministic - same input ALWAYS gives same output.
"""
from sqlalchemy.orm import Session
from sqlalchemy import func, and_
from datetime import date
from typing import List, Optional
from .models import SiteMonthMetric
from .schemas import MetricPoint, TimeseriesResponse, SummaryResponse


def get_timeseries(
    db: Session,
    site_ids: List[str],
    metric_names: List[str],
    from_date: date,
    to_date: date,
    data_version: Optional[str] = None
) -> TimeseriesResponse:
    """
    Fetch time series data for specified sites and metrics.

    Args:
        db: Database session
        site_ids: List of site IDs to include
        metric_names: List of metric names to fetch
        from_date: Start date (inclusive)
        to_date: End date (inclusive)
        data_version: Optional data version filter

    Returns:
        TimeseriesResponse with all matching points
    """
    query = db.query(SiteMonthMetric)

    # Apply filters
    filters = [
        SiteMonthMetric.site_id.in_(site_ids),
        SiteMonthMetric.metric_name.in_(metric_names),
        SiteMonthMetric.month_start >= from_date,
        SiteMonthMetric.month_start <= to_date
    ]

    if data_version:
        filters.append(SiteMonthMetric.data_version == data_version)

    query = query.filter(and_(*filters))

    # Order by time, then site
    query = query.order_by(
        SiteMonthMetric.month_start,
        SiteMonthMetric.site_id,
        SiteMonthMetric.metric_name
    )

    results = query.all()

    points = [
        MetricPoint(
            site_id=r.site_id,
            site_name=r.site_name,
            month_start=r.month_start,
            metric_name=r.metric_name,
            metric_value=r.metric_value,
            unit=r.unit
        )
        for r in results
    ]

    return TimeseriesResponse(
        points=points,
        total_points=len(points),
        sites=list(set(r.site_id for r in results)),
        metrics=list(set(r.metric_name for r in results))
    )


def get_summary(
    db: Session,
    site_id: Optional[str],
    metric_name: str,
    from_date: date,
    to_date: date,
    aggregation: str = "avg",
    data_version: Optional[str] = None
) -> SummaryResponse:
    """
    Get aggregated summary for a metric over a time period.

    Args:
        db: Database session
        site_id: Site ID (None for all sites)
        metric_name: Metric name to aggregate
        from_date: Start date
        to_date: End date
        aggregation: "sum", "avg", "min", "max"
        data_version: Optional data version filter

    Returns:
        SummaryResponse with aggregated value
    """
    # Build base query
    query = db.query(SiteMonthMetric)

    filters = [
        SiteMonthMetric.metric_name == metric_name,
        SiteMonthMetric.month_start >= from_date,
        SiteMonthMetric.month_start <= to_date
    ]

    if site_id:
        filters.append(SiteMonthMetric.site_id == site_id)

    if data_version:
        filters.append(SiteMonthMetric.data_version == data_version)

    query = query.filter(and_(*filters))

    # Apply aggregation function
    agg_map = {
        "sum": func.sum,
        "avg": func.avg,
        "min": func.min,
        "max": func.max
    }

    if aggregation not in agg_map:
        raise ValueError(f"Invalid aggregation: {aggregation}. Must be one of {list(agg_map.keys())}")

    agg_func = agg_map[aggregation]

    # Execute aggregation
    result = query.with_entities(
        agg_func(SiteMonthMetric.metric_value).label('agg_value'),
        func.count().label('data_points'),
        func.first_value(SiteMonthMetric.unit).label('unit'),
        func.first_value(SiteMonthMetric.site_id).label('site_id'),
        func.first_value(SiteMonthMetric.site_name).label('site_name')
    ).first()

    if not result or result.agg_value is None:
        raise ValueError(f"No data found for {metric_name} between {from_date} and {to_date}")

    return SummaryResponse(
        site_id=result.site_id if site_id else None,
        site_name=result.site_name if site_id else "All Sites",
        metric_name=metric_name,
        unit=result.unit or "",
        aggregation=aggregation,
        value=float(result.agg_value),
        from_date=from_date,
        to_date=to_date,
        data_points=result.data_points
    )


def get_site_list(db: Session, data_version: Optional[str] = None) -> List[dict]:
    """Get list of all available sites"""
    query = db.query(
        SiteMonthMetric.site_id,
        SiteMonthMetric.site_name
    ).distinct()

    if data_version:
        query = query.filter(SiteMonthMetric.data_version == data_version)

    results = query.all()
    return [{"site_id": r.site_id, "site_name": r.site_name} for r in results]


def get_metric_list(db: Session, data_version: Optional[str] = None) -> List[dict]:
    """Get list of all available metrics"""
    query = db.query(
        SiteMonthMetric.metric_name,
        SiteMonthMetric.unit
    ).distinct()

    if data_version:
        query = query.filter(SiteMonthMetric.data_version == data_version)

    results = query.all()
    return [{"metric_name": r.metric_name, "unit": r.unit} for r in results]


def get_ranking(
    db: Session,
    metric_name: str,
    from_date: date,
    to_date: date,
    top_n: int = 5,
    ascending: bool = False,
    data_version: Optional[str] = None
) -> List[SummaryResponse]:
    """
    Get top/bottom N sites for a metric.

    Args:
        db: Database session
        metric_name: Metric to rank by
        from_date: Start date
        to_date: End date
        top_n: Number of sites to return
        ascending: True for bottom N, False for top N
        data_version: Optional data version filter

    Returns:
        List of SummaryResponse ordered by metric value
    """
    query = db.query(
        SiteMonthMetric.site_id,
        SiteMonthMetric.site_name,
        func.sum(SiteMonthMetric.metric_value).label('total_value'),
        func.count().label('data_points'),
        func.first_value(SiteMonthMetric.unit).label('unit')
    ).filter(
        SiteMonthMetric.metric_name == metric_name,
        SiteMonthMetric.month_start >= from_date,
        SiteMonthMetric.month_start <= to_date
    )

    if data_version:
        query = query.filter(SiteMonthMetric.data_version == data_version)

    query = query.group_by(
        SiteMonthMetric.site_id,
        SiteMonthMetric.site_name
    )

    # Order by total value
    if ascending:
        query = query.order_by(func.sum(SiteMonthMetric.metric_value).asc())
    else:
        query = query.order_by(func.sum(SiteMonthMetric.metric_value).desc())

    results = query.limit(top_n).all()

    return [
        SummaryResponse(
            site_id=r.site_id,
            site_name=r.site_name,
            metric_name=metric_name,
            unit=r.unit or "",
            aggregation="sum",
            value=float(r.total_value),
            from_date=from_date,
            to_date=to_date,
            data_points=r.data_points
        )
        for r in results
    ]
