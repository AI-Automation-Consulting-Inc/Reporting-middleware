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
    show_rep_breakdown: bool = False,
    llm_chart_hint: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Build an appropriate chart based on the intent structure and result data.
    
    Args:
        intent: The validated intent dict with metric, filters, group_by, date_range
        results: List of row dicts from SQL execution
        output_path: Optional path to save HTML file (default: last_chart.html)
        include_base64: If True, include base64-encoded HTML in return dict
        show_rep_breakdown: If True and group_by is region, fetch per-rep data for grouped bars
        llm_chart_hint: Optional LLM-selected chart type and options
    
    Returns:
        Dict with 'chart_type', 'html_path', and optionally 'html_base64'
    """
    if not results:
        return {
            "chart_type": "none",
            "message": "No data to chart",
            "html_path": None,
        }
    
    print(f"[CHART] Building chart for intent: group_by={intent.get('group_by')}, metric={intent.get('metric')}, has_derived_expr={bool(intent.get('derived_expression'))}")
    print(f"[CHART] Derived expression: {intent.get('derived_expression', 'None')}")
    
    # Use LLM-selected strategy if provided, otherwise infer from structure
    if llm_chart_hint and llm_chart_hint.get("chart_type"):
        strategy = llm_chart_hint["chart_type"]
        print(f"[CHART] Using LLM-selected strategy: {strategy}")
    else:
        strategy = _infer_chart_strategy(intent, results)
        print(f"[CHART] Using inferred strategy: {strategy}")
    
    metric_name = intent.get("metric", "metric")
    
    if strategy == "kpi":
        fig = _build_kpi_chart(results, metric_name)
    elif strategy == "line":
        fig = _build_line_chart(results, metric_name, intent)
    elif strategy == "grouped_bar":
        # LLM explicitly requested grouped bars for breakdown
        print(f"[CHART] Strategy=grouped_bar, forcing show_rep_breakdown=True")
        fig = _build_bar_chart(results, metric_name, intent, show_rep_breakdown=True)
    elif strategy == "bar":
        print(f"[CHART] Strategy=bar, show_rep_breakdown={show_rep_breakdown}")
        fig = _build_bar_chart(results, metric_name, intent, show_rep_breakdown=show_rep_breakdown)
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
    
    # Check if metric is currency-based
    is_currency = any(term in metric_name.lower() for term in ['revenue', 'arr', 'acv', 'margin', 'cost', 'price', 'value'])
    value_format = '$,.2f' if is_currency else ',.2f'
    
    fig = go.Figure(go.Indicator(
        mode="number",
        value=value,
        title={"text": metric_name.replace("_", " ").title()},
        number={'valueformat': value_format, 'prefix': '$' if is_currency else ''},
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


def _build_bar_chart(results: List[Dict[str, Any]], metric_name: str, intent: Dict[str, Any], show_rep_breakdown: bool = False) -> go.Figure:
    """Build a bar chart for group_by dimension comparisons."""
    group_by = intent.get("group_by", "Category")

    # Only render grouped rep breakdown when explicitly requested via flag/LLM hint
    if show_rep_breakdown and group_by == "region":
        print(f"[CHART] show_rep_breakdown=True → grouped bar by rep")
        return _build_grouped_bar_by_rep(results, metric_name, intent)
    
    categories = [r.get("group_col", f"Row {i}") for i, r in enumerate(results)]
    values = [r.get("metric", 0) for r in results]
    
    # Check if metric is currency-based
    is_currency = any(term in metric_name.lower() for term in ['revenue', 'arr', 'acv', 'margin', 'cost', 'price', 'value'])
    value_format = '$%{text:,.2f}' if is_currency else '%{text:,.2f}'
    
    # Build title with filter context
    title_parts = [f"{metric_name.replace('_', ' ').title()} by {group_by.replace('_', ' ').title()}"]
    filters = intent.get('filters', {})
    if filters:
        filter_desc = ", ".join([f"{k.replace('_', ' ').title()}: {v}" for k, v in filters.items()])
        title_parts.append(f"({filter_desc})")
    chart_title = " ".join(title_parts)
    
    fig = go.Figure(go.Bar(
        x=categories,
        y=values,
        name=metric_name.replace("_", " ").title(),
        text=values,
        texttemplate=value_format,
        textposition='outside',
        hovertemplate=f'<b>%{{x}}</b><br>{metric_name}: {"$" if is_currency else ""}%{{y:,.2f}}<extra></extra>',
    ))
    
    fig.update_layout(
        title=chart_title,
        xaxis_title=group_by.replace("_", " ").title(),
        yaxis_title=metric_name.replace("_", " ").title(),
        yaxis=dict(tickformat='$,.2f' if is_currency else ',.2f'),
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


def _build_grouped_bar_by_rep(results: List[Dict[str, Any]], metric_name: str, intent: Dict[str, Any]) -> go.Figure:
    """Build a grouped bar chart showing per-rep revenue by region."""
    from pathlib import Path
    from sqlalchemy import create_engine, text
    
    # Re-query with group_by region + rep to get breakdown data
    try:
        engine = create_engine('sqlite:///enhanced_sales.db')
        
        # Build a query that groups by region and rep
        start_date = intent.get("resolved_dates", {}).get("start_date")
        end_date = intent.get("resolved_dates", {}).get("end_date")
        
        if not start_date or not end_date:
            # Fallback to simple bar if dates unavailable
            return _build_bar_chart(results, metric_name, intent, show_rep_breakdown=False)
        
        # Query: SUM(net_revenue) by region and rep
        query = text("""
            SELECT 
                d.country AS region,
                sr.rep_name AS rep,
                SUM(f.net_revenue) AS revenue
            FROM fact_sales_pipeline f
            JOIN dim_region d ON f.region_id = d.region_id
            JOIN dim_sales_rep sr ON f.sales_rep_id = sr.sales_rep_id
            WHERE f.sale_date >= :start_date AND f.sale_date <= :end_date
            GROUP BY d.country, sr.rep_name
            ORDER BY d.country, revenue DESC
        """)
        
        with engine.connect() as conn:
            res = conn.execute(query, {"start_date": start_date, "end_date": end_date})
            breakdown_rows = [dict(r._mapping) for r in res]
        
        if not breakdown_rows:
            # No breakdown data, fallback to simple bar
            return _build_bar_chart(results, metric_name, intent, show_rep_breakdown=False)
        
        # Build grouped bar: one trace per rep
        import pandas as pd
        df = pd.DataFrame(breakdown_rows)
        
        fig = go.Figure()
        
        for rep in df['rep'].unique():
            rep_data = df[df['rep'] == rep]
            fig.add_trace(go.Bar(
                name=rep,
                x=rep_data['region'],
                y=rep_data['revenue'],
                text=rep_data['revenue'],
                texttemplate='$%{text:,.2f}',
                textposition='outside',
                hovertemplate='<b>%{fullData.name}</b><br>Revenue: $%{y:,.2f}<extra></extra>',
            ))
        
        fig.update_layout(
            title=f"Revenue by Sales Rep and Region",
            xaxis_title="Region",
            yaxis_title="Revenue",
            barmode='group',
            legend_title="Sales Rep",
            hovermode='x unified',
            yaxis=dict(tickformat='$,.2f'),
        )
        
        return fig
        
    except Exception as e:
        # Fallback to simple bar on any error
        print(f"[CHART] Rep breakdown failed: {e}, falling back to simple bar")
        return _build_bar_chart(results, metric_name, intent, show_rep_breakdown=False)


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
