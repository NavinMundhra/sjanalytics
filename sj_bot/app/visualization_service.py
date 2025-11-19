"""
Visualization service - generates PNG charts from data.

Uses matplotlib to create professional charts for WhatsApp delivery.
All functions are deterministic - same data always produces same chart.
"""
import matplotlib
matplotlib.use('Agg')  # Non-interactive backend for server use

import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import date, datetime
from typing import List
from io import BytesIO
import pandas as pd


# Set default style
plt.style.use('seaborn-v0_8-darkgrid')

# Professional color palette
COLORS = ['#2E86AB', '#A23B72', '#F18F01', '#C73E1D', '#5F9EA0', '#8B4789', '#D4A373']


def render_timeseries_chart(
    title: str,
    x: List[date],
    series: List[dict],  # [{"label": str, "values": list[float]}]
    y_label: str,
    width_px: int = 1200,
    height_px: int = 800,
) -> bytes:
    """
    Render a time series line chart as PNG bytes.

    Args:
        title: Chart title
        x: List of dates for x-axis
        series: List of dicts with {"label": str, "values": list[float]}
        y_label: Y-axis label
        width_px: Chart width in pixels
        height_px: Chart height in pixels

    Returns:
        PNG image as bytes
    """
    # Calculate figure size in inches (assuming 100 DPI)
    dpi = 150
    fig_width = width_px / dpi
    fig_height = height_px / dpi

    fig, ax = plt.subplots(figsize=(fig_width, fig_height), dpi=dpi)

    # Plot each series
    for idx, s in enumerate(series):
        label = s.get('label', f'Series {idx + 1}')
        values = s.get('values', [])
        color = COLORS[idx % len(COLORS)]

        ax.plot(
            x,
            values,
            marker='o',
            linewidth=2.5,
            markersize=6,
            label=label,
            color=color
        )

        # Add value labels for last point
        if values:
            last_x = x[-1]
            last_y = values[-1]
            ax.annotate(
                f'{last_y:,.0f}',
                xy=(last_x, last_y),
                xytext=(10, 0),
                textcoords='offset points',
                fontsize=9,
                color=color,
                fontweight='bold'
            )

    # Formatting
    ax.set_title(title, fontsize=16, fontweight='bold', pad=20)
    ax.set_xlabel('Month', fontsize=12)
    ax.set_ylabel(y_label, fontsize=12)

    # Format x-axis dates
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%b %Y'))
    plt.xticks(rotation=45, ha='right')

    # Format y-axis with comma separators
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f'{x:,.0f}'))

    # Grid
    ax.grid(True, alpha=0.3, linestyle='--')

    # Legend
    if len(series) > 1:
        ax.legend(loc='best', framealpha=0.9, fontsize=10)

    # Tight layout
    plt.tight_layout()

    # Save to bytes
    buf = BytesIO()
    plt.savefig(buf, format='png', dpi=dpi, bbox_inches='tight')
    plt.close(fig)

    buf.seek(0)
    return buf.read()


def render_bar_chart(
    title: str,
    categories: List[str],
    values: List[float],
    y_label: str,
    width_px: int = 1200,
    height_px: int = 800,
) -> bytes:
    """
    Render a bar chart as PNG bytes.

    Args:
        title: Chart title
        categories: Labels for each bar
        values: Values for each bar
        y_label: Y-axis label
        width_px: Chart width
        height_px: Chart height

    Returns:
        PNG image as bytes
    """
    dpi = 150
    fig_width = width_px / dpi
    fig_height = height_px / dpi

    fig, ax = plt.subplots(figsize=(fig_width, fig_height), dpi=dpi)

    # Create bars with different colors
    bars = ax.bar(
        categories,
        values,
        color=COLORS[:len(categories)],
        edgecolor='black',
        linewidth=0.5
    )

    # Add value labels on top of bars
    for bar in bars:
        height = bar.get_height()
        ax.annotate(
            f'{height:,.0f}',
            xy=(bar.get_x() + bar.get_width() / 2, height),
            xytext=(0, 5),
            textcoords='offset points',
            ha='center',
            fontsize=10,
            fontweight='bold'
        )

    # Formatting
    ax.set_title(title, fontsize=16, fontweight='bold', pad=20)
    ax.set_ylabel(y_label, fontsize=12)
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f'{x:,.0f}'))

    # Rotate x labels if many categories
    if len(categories) > 5:
        plt.xticks(rotation=45, ha='right')

    ax.grid(axis='y', alpha=0.3, linestyle='--')
    plt.tight_layout()

    buf = BytesIO()
    plt.savefig(buf, format='png', dpi=dpi, bbox_inches='tight')
    plt.close(fig)

    buf.seek(0)
    return buf.read()


def render_comparison_chart(
    title: str,
    categories: List[str],
    series: List[dict],  # [{"label": str, "values": list[float]}]
    y_label: str,
    width_px: int = 1200,
    height_px: int = 800,
) -> bytes:
    """
    Render grouped bar chart for comparisons.

    Args:
        title: Chart title
        categories: X-axis categories
        series: List of series to compare
        y_label: Y-axis label
        width_px: Width in pixels
        height_px: Height in pixels

    Returns:
        PNG image as bytes
    """
    dpi = 150
    fig_width = width_px / dpi
    fig_height = height_px / dpi

    fig, ax = plt.subplots(figsize=(fig_width, fig_height), dpi=dpi)

    x = range(len(categories))
    width = 0.8 / len(series)  # Bar width

    for idx, s in enumerate(series):
        label = s.get('label', f'Series {idx + 1}')
        values = s.get('values', [])
        offset = (idx - len(series)/2 + 0.5) * width

        ax.bar(
            [i + offset for i in x],
            values,
            width,
            label=label,
            color=COLORS[idx % len(COLORS)]
        )

    ax.set_title(title, fontsize=16, fontweight='bold', pad=20)
    ax.set_ylabel(y_label, fontsize=12)
    ax.set_xticks(x)
    ax.set_xticklabels(categories, rotation=45, ha='right')
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f'{x:,.0f}'))
    ax.legend(loc='best', framealpha=0.9)
    ax.grid(axis='y', alpha=0.3, linestyle='--')

    plt.tight_layout()

    buf = BytesIO()
    plt.savefig(buf, format='png', dpi=dpi, bbox_inches='tight')
    plt.close(fig)

    buf.seek(0)
    return buf.read()
