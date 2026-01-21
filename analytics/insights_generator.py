"""
AI-powered insights generator.

Uses GPT-4 with higher temperature (0.75) for creative analysis
while staying grounded in actual query results.
"""
from __future__ import annotations

import os
import json
from typing import Dict, List, Any
from textwrap import dedent

try:
    from openai import OpenAI
except ImportError as exc:
    raise RuntimeError(
        "openai package not installed. Run `pip install openai` in your environment."
    ) from exc


INSIGHTS_MODEL = os.getenv("OPENAI_INSIGHTS_MODEL", "gpt-4o")
INSIGHTS_TEMPERATURE = 0.75


def generate_insights(
    question: str,
    intent: Dict[str, Any],
    rows: List[Dict[str, Any]],
    config: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Generate AI-powered insights from query results.
    
    Args:
        question: Original user question
        intent: Parsed intent (metric, filters, group_by, etc.)
        rows: Query result rows
        config: Tenant configuration
        
    Returns:
        Dictionary with insights:
        {
            "key_findings": ["Finding 1", "Finding 2"],
            "trends": ["Trend observation"],
            "anomalies": ["Anomaly detected"],
            "recommendations": ["Actionable recommendation"]
        }
    """
    if not rows:
        return {
            "key_findings": ["No data returned for this query."],
            "trends": [],
            "anomalies": [],
            "recommendations": ["Try broadening your date range or removing filters."]
        }
    
    # Limit rows sent to LLM to avoid token overflow
    sample_rows = rows[:50]
    
    # Build context
    metric_name = intent.get("metric", "unknown")
    group_by = intent.get("group_by")
    filters = intent.get("filters", {})
    date_range = intent.get("date_range", "unknown period")
    
    system_prompt = dedent("""
        You are a data analyst generating insights from SaaS business metrics.
        Given a query and its results, provide concise, actionable insights.
        
        Output ONLY a JSON object with these fields:
        {
            "key_findings": ["2-3 most important data points"],
            "trends": ["1-2 trend observations if applicable"],
            "anomalies": ["1-2 anomalies or outliers if detected"],
            "recommendations": ["1-2 actionable recommendations"]
        }
        
        Rules:
        - Use specific numbers and percentages from the data
        - Compare top performers vs average when grouping
        - Identify growth rates for time-series data
        - Flag outliers (values significantly above/below average)
        - Keep each insight to 1 sentence
        - Be specific, not generic
        - Only include fields that have meaningful content
    """).strip()
    
    user_prompt = dedent(f"""
        Question: {question}
        
        Query Details:
        - Metric: {metric_name}
        - Grouped by: {group_by or "N/A (summary metric)"}
        - Filters: {json.dumps(filters) if filters else "None"}
        - Date range: {date_range}
        
        Results ({len(rows)} total rows, showing first {len(sample_rows)}):
        {json.dumps(sample_rows, indent=2)}
        
        Generate insights as JSON.
    """).strip()
    
    try:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            return {
                "key_findings": ["Insights generation unavailable (API key not configured)."],
                "trends": [],
                "anomalies": [],
                "recommendations": []
            }
        
        client = OpenAI(api_key=api_key)
        
        response = client.chat.completions.create(
            model=INSIGHTS_MODEL,
            temperature=INSIGHTS_TEMPERATURE,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            response_format={"type": "json_object"}
        )
        
        insights_json = response.choices[0].message.content
        insights = json.loads(insights_json)
        
        # Validate structure
        result = {
            "key_findings": insights.get("key_findings", []),
            "trends": insights.get("trends", []),
            "anomalies": insights.get("anomalies", []),
            "recommendations": insights.get("recommendations", [])
        }
        
        return result
        
    except Exception as e:
        print(f"[INSIGHTS] Error generating insights: {e}")
        import traceback
        traceback.print_exc()
        
        # Return basic fallback insights
        return _generate_fallback_insights(metric_name, group_by, rows)


def _generate_fallback_insights(metric_name: str, group_by: str, rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Generate simple insights without LLM when API fails."""
    findings = []
    
    if not rows:
        return {"key_findings": ["No data available."], "trends": [], "anomalies": [], "recommendations": []}
    
    # Summary metric
    if not group_by or group_by == "null":
        metric_value = rows[0].get("metric", 0)
        findings.append(f"Total {metric_name}: {metric_value:,.2f}")
    
    # Grouped results
    else:
        top_item = rows[0] if rows else None
        if top_item:
            group_name = top_item.get("group_col", "Unknown")
            metric_value = top_item.get("metric", 0)
            findings.append(f"Top performer: {group_name} with {metric_value:,.2f} {metric_name}")
        
        if len(rows) > 1:
            findings.append(f"Analysis covers {len(rows)} distinct {group_by} values")
    
    return {
        "key_findings": findings,
        "trends": [],
        "anomalies": [],
        "recommendations": ["Review top performers for best practices."]
    }


__all__ = ["generate_insights"]
