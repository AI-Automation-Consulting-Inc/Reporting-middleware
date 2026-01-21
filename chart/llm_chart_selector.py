"""LLM-powered chart type selector for complex queries."""
from __future__ import annotations

import json
import os
from typing import Dict, Any, Optional

def select_chart_type_with_llm(question: str, intent: Dict[str, Any], results: list) -> Dict[str, Any]:
    """
    Use LLM to determine the best chart type and options for a given query.
    
    Returns a dict with:
    - chart_type: one of 'bar', 'grouped_bar', 'line', 'pie', 'kpi', 'table'
    - chart_options: dict with additional rendering hints (e.g., show_breakdown=True)
    """
    from openai import OpenAI
    
    client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
    
    # Prepare context for LLM
    data_summary = {
        "row_count": len(results),
        "columns": list(results[0].keys()) if results else [],
        "sample_row": results[0] if results else {},
        "intent": intent,
    }
    
    prompt = f"""You are a data visualization expert. Given a user's natural language question and the query results, determine the best chart type.

User question: "{question}"

Query intent: {json.dumps(intent, indent=2)}

Data summary:
- Rows: {data_summary['row_count']}
- Columns: {data_summary['columns']}
- Sample: {json.dumps(data_summary['sample_row'], indent=2)}

Chart type options:
- "kpi": Single metric summary (no grouping)
- "bar": Simple bar chart (one value per category)
- "grouped_bar": Grouped/clustered bars (show breakdown by sub-dimension)
- "line": Trend over time
- "pie": Proportional breakdown (<=6 categories)
- "table": Fallback for complex data

Additional options you can specify:
- show_breakdown: true if the user wants to see sub-category breakdowns (e.g., "revenue per sales person BY region" should show individual reps within each region)
- breakdown_dimension: which dimension to use for grouping (e.g., "sales_rep", "product")

CRITICAL: Base your chart selection ONLY on the actual data returned and the intent structure. Do NOT invent or assume data that isn't present.

Rules:
1. If question asks for "per X by Y" or "breakdown by Y showing X", use grouped_bar with show_breakdown=true
2. If question mentions "each", "individual", "breakdown", prefer grouped visualizations
3. For time series (monthly, quarterly), use line
4. For single summary metrics, use kpi
5. For simple category comparisons, use bar

Return ONLY valid JSON with this structure:
{{
  "chart_type": "bar|grouped_bar|line|pie|kpi|table",
  "chart_options": {{
    "show_breakdown": true|false,
    "breakdown_dimension": "dimension_name|null"
  }},
  "reasoning": "Brief explanation of your choice"
}}"""

    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=500,
            temperature=0.2,
            response_format={"type": "json_object"}
        )
        
        text = response.choices[0].message.content.strip()
        
        # Parse JSON response
        result = json.loads(text)
        
        print(f"[CHART_LLM] Selected: {result.get('chart_type')} - {result.get('reasoning')}")
        
        return result
        
    except Exception as e:
        print(f"[CHART_LLM] Failed to select chart type: {e}, using fallback")
        import traceback
        traceback.print_exc()
        # Fallback to simple heuristics
        group_by = intent.get("group_by")
        if not group_by:
            return {"chart_type": "kpi", "chart_options": {}, "reasoning": "No grouping - fallback to KPI"}
        elif group_by == "month":
            return {"chart_type": "line", "chart_options": {}, "reasoning": "Time series - fallback to line"}
        else:
            return {"chart_type": "bar", "chart_options": {}, "reasoning": "Category grouping - fallback to bar"}


__all__ = ["select_chart_type_with_llm"]
