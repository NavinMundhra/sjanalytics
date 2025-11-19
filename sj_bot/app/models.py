"""SQLAlchemy ORM models"""
from sqlalchemy import Column, Integer, String, Float, Date, DateTime, Index
from sqlalchemy.sql import func
from .db import Base


class SiteMonthMetric(Base):
    """
    Core metrics table storing monthly site-level data.

    Design principles:
    - Narrow table: one row per site-month-metric combination
    - Easy to query, filter, and aggregate
    - Supports versioning for data refreshes
    """
    __tablename__ = "site_month_metrics"

    id = Column(Integer, primary_key=True, index=True)

    # Site identifiers
    site_id = Column(String, nullable=False, index=True)
    site_name = Column(String, nullable=False)

    # Time dimension
    month_start = Column(Date, nullable=False, index=True)  # First day of month
    fy_label = Column(String, index=True)  # e.g., "FY24-25"

    # Metric
    metric_name = Column(String, nullable=False, index=True)  # e.g., "chiller_kwh_trh"
    metric_value = Column(Float, nullable=False)
    unit = Column(String)  # "kWh", "kWh/TRh", "L", "₹", etc.

    # Data lineage
    data_version = Column(String, index=True, default="default")  # For refresh tracking
    created_at = Column(DateTime, server_default=func.now())

    # Composite indexes for common query patterns
    __table_args__ = (
        Index('idx_site_month_metric', 'site_id', 'month_start', 'metric_name'),
        Index('idx_month_metric', 'month_start', 'metric_name'),
        Index('idx_version_metric', 'data_version', 'metric_name'),
    )

    def __repr__(self):
        return f"<SiteMonthMetric(site={self.site_id}, month={self.month_start}, metric={self.metric_name}, value={self.metric_value})>"
