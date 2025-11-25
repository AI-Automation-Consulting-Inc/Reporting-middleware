"""
Chart builder for analytics results.

This module infers chart type from the intent structure and generates
interactive Plotly charts saved as standalone HTML files.
"""
from __future__ import annotations

import base64
from pathlib import Path
from typing import Dict, Any, List, Optional

import plotly.graph_objects as go
import plotly.express as px


class ChartBuilderError(ValueError):
    pass


def build_chart(
    intent: Dict[str, Any],
    results: List[Dict[str, Any]],
    output_path: Optional[str] = None,
    include_base64: bool = False,
) -> Dict[str, Any]:
    """
    Build an appropriate chart based on the intent structure and result data.
    
    Args:
        intent: The validated intent dict with metric, filters, group_by, date_range
        results: List of row dicts from SQL execution
        output_path: Optional path to save HTML file (default: last_chart.html)
        include_base64: If True, include base64-encoded HTML in return dict
    
    Returns:
        Dict with 'chart_type', 'html_path', and optionally 'html_base64'
    """
    if not results:
        return {
            "chart_type": "none",
            "message": "No data to chart",
            "html_path": None,
        }
    
    strategy = _infer_chart_strategy(intent, results)
    metric_name = intent.get("metric", "metric")
    
    if strategy == "kpi":
        fig = _build_kpi_chart(results, metric_name)
    elif strategy == "line":
        fig = _build_line_chart(results, metric_name, intent)
    elif strategy == "bar":
        fig = _build_bar_chart(results, metric_name, intent)
    elif strategy == "pie":
        fig = _build_pie_chart(results, metric_name, intent)
    elif strategy == "area":
        fig = _build_area_chart(results, metric_name, intent)
    else:
        # Fallback to table
        fig = _build_table_chart(results)
        strategy = "table"
    
    # Save HTML
    if output_path is None:
        output_path = "last_chart.html"
    
    html_str = fig.to_html(include_plotlyjs='cdn', full_html=True)
    Path(output_path).write_text(html_str, encoding='utf-8')
    
    result = {
        "chart_type": strategy,
        "html_path": str(Path(output_path).absolute()),
    }
    
    if include_base64:
        result["html_base64"] = base64.b64encode(html_str.encode('utf-8')).decode('utf-8')
    
    return result


def _infer_chart_strategy(intent: Dict[str, Any], results: List[Dict[str, Any]]) -> str:
    """
    Infer the best chart type based on intent structure and data.
    
    Rules:
    - summary (no group_by) → KPI card
    - trend (group_by='month') → line or area chart
    - group_by dimension → bar chart (or pie if <=6 categories)
    """
    group_by = intent.get("group_by")
    
    # Summary metric → KPI
    if not group_by:
        return "kpi"
    
    # Trend over time → line chart (area optional)
    if group_by == "month":
        return "line"  # could add logic to prefer area for cumulative metrics
    
    # Group by dimension → bar or pie
    if len(results) <= 6:
        # Small category count → pie might work, but bar is safer default
        return "bar"
    
    return "bar"


def _build_kpi_chart(results: List[Dict[str, Any]], metric_name: str) -> go.Figure:
    """Build a KPI indicator card for a single summary value."""
    value = results[0].get("metric", 0)
    
    fig = go.Figure(go.Indicator(
        mode="number",
        value=value,
        title={"text": metric_name.replace("_", " ").title()},
        number={'valueformat': ',.2f'},
    ))
    
    fig.update_layout(
        height=300,
        margin=dict(l=20, r=20, t=60, b=20),
    )
    
    return fig


def _build_line_chart(results: List[Dict[str, Any]], metric_name: str, intent: Dict[str, Any]) -> go.Figure:
    """Build a line chart for trend data (group_by='month')."""
    months = [r.get("month") for r in results]
    values = [r.get("metric", 0) for r in results]
    
    # Check if there's a secondary grouping (e.g., trend by product and month)
    group_col = [r.get("group_col") for r in results]
    if group_col and group_col[0]:
        # Multi-line chart
        import pandas as pd
        df = pd.DataFrame(results)
        fig = px.line(
            df,
            x="month",
            y="metric",
            color="group_col",
            title=f"{metric_name.replace('_', ' ').title()} Over Time",
            labels={"metric": metric_name.replace("_", " ").title(), "month": "Month"},
        )
    else:
        # Single-line chart
        fig = go.Figure(go.Scatter(
            x=months,
            y=values,
            mode='lines+markers',
            name=metric_name.replace("_", " ").title(),
        ))
        
        fig.update_layout(
            title=f"{metric_name.replace('_', ' ').title()} Over Time",
            xaxis_title="Month",
            yaxis_title=metric_name.replace("_", " ").title(),
            hovermode='x unified',
        )
    
    return fig


def _build_bar_chart(results: List[Dict[str, Any]], metric_name: str, intent: Dict[str, Any]) -> go.Figure:
    """Build a bar chart for group_by dimension comparisons."""
    categories = [r.get("group_col", f"Row {i}") for i, r in enumerate(results)]
    values = [r.get("metric", 0) for r in results]
    
    fig = go.Figure(go.Bar(
        x=categories,
        y=values,
        name=metric_name.replace("_", " ").title(),
        text=values,
        texttemplate='%{text:,.2f}',
        textposition='outside',
    ))
    
    group_by = intent.get("group_by", "Category")
    fig.update_layout(
        title=f"{metric_name.replace('_', ' ').title()} by {group_by.replace('_', ' ').title()}",
        xaxis_title=group_by.replace("_", " ").title(),
        yaxis_title=metric_name.replace("_", " ").title(),
        showlegend=False,
    )
    
    return fig


def _build_pie_chart(results: List[Dict[str, Any]], metric_name: str, intent: Dict[str, Any]) -> go.Figure:
    """Build a pie chart for group_by dimension (small category count)."""
    labels = [r.get("group_col", f"Row {i}") for i, r in enumerate(results)]
    values = [r.get("metric", 0) for r in results]
    
    fig = go.Figure(go.Pie(
        labels=labels,
        values=values,
        textinfo='label+percent',
        hoverinfo='label+value',
    ))
    
    group_by = intent.get("group_by", "Category")
    fig.update_layout(
        title=f"{metric_name.replace('_', ' ').title()} by {group_by.replace('_', ' ').title()}",
    )
    
    return fig


def _build_area_chart(results: List[Dict[str, Any]], metric_name: str, intent: Dict[str, Any]) -> go.Figure:
    """Build an area chart for trend data (similar to line but filled)."""
    months = [r.get("month") for r in results]
    values = [r.get("metric", 0) for r in results]
    
    fig = go.Figure(go.Scatter(
        x=months,
        y=values,
        mode='lines',
        fill='tozeroy',
        name=metric_name.replace("_", " ").title(),
    ))
    
    fig.update_layout(
        title=f"{metric_name.replace('_', ' ').title()} Over Time (Area)",
        xaxis_title="Month",
        yaxis_title=metric_name.replace("_", " ").title(),
        hovermode='x unified',
    )
    
    return fig


def _build_table_chart(results: List[Dict[str, Any]]) -> go.Figure:
    """Build a table view for data that doesn't fit other chart types."""
    if not results:
        return go.Figure()
    
    # Extract column names from first row
    columns = list(results[0].keys())
    
    # Build table data
    table_data = []
    for col in columns:
        table_data.append([r.get(col, "") for r in results])
    
    fig = go.Figure(go.Table(
        header=dict(
            values=[col.replace("_", " ").title() for col in columns],
            fill_color='paleturquoise',
            align='left',
        ),
        cells=dict(
            values=table_data,
            fill_color='lavender',
            align='left',
        ),
    ))
    
    fig.update_layout(
        title="Query Results",
        height=min(600, 50 + len(results) * 30),
    )
    
    return fig


__all__ = ["build_chart", "ChartBuilderError"]
