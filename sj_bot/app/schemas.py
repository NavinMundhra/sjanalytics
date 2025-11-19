"""Pydantic schemas for request/response validation"""
from pydantic import BaseModel, Field
from datetime import date
from typing import List, Optional


class MetricPoint(BaseModel):
    """Single data point in a time series"""
    site_id: str
    site_name: str
    month_start: date
    metric_name: str
    metric_value: float
    unit: str

    class Config:
        from_attributes = True


class TimeseriesResponse(BaseModel):
    """Response for timeseries queries"""
    points: List[MetricPoint]
    total_points: int
    sites: List[str]
    metrics: List[str]


class SummaryResponse(BaseModel):
    """Response for aggregated summary queries"""
    site_id: Optional[str] = None
    site_name: Optional[str] = None
    metric_name: str
    unit: str
    aggregation: str  # "sum", "avg", "min", "max"
    value: float
    from_date: date
    to_date: date
    data_points: int


class TimeseriesChartRequest(BaseModel):
    """Request to generate a time series chart"""
    title: str
    x: List[str]  # Date strings or labels
    series: List[dict]  # [{"label": str, "values": list[float]}]
    y_label: str
    width_px: int = Field(default=1200, ge=400, le=2000)
    height_px: int = Field(default=800, ge=300, le=1500)


class BotQuery(BaseModel):
    """User query to the bot"""
    user_id: str
    message: str
    context: Optional[dict] = None


class BotResponse(BaseModel):
    """Bot's response to user query"""
    text: str
    chart_png: Optional[str] = None  # Base64 encoded
    chart_url: Optional[str] = None
    data: Optional[dict] = None
