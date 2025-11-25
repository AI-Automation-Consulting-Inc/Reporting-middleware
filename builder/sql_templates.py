"""
Deterministic SQL templates for analytic queries.
"""
from string import Template


TREND_TEMPLATE = Template(
    """
    SELECT
        strftime('%Y-%m', $date_column) AS period,
        SUM($metric_formula) AS value
    FROM $fact_table
    WHERE 1=1
        $filters
        AND $date_column BETWEEN '$start_date' AND '$end_date'
    GROUP BY 1
    ORDER BY 1 ASC
    """
)

SUMMARY_TEMPLATE = Template(
    """
    SELECT
        SUM($metric_formula) AS value
    FROM $fact_table
    WHERE 1=1
        $filters
        AND $date_column BETWEEN '$start_date' AND '$end_date'
    """
)

GROUP_BY_TEMPLATE = Template(
    """
    SELECT
        $group_by AS label,
        SUM($metric_formula) AS value
    FROM $fact_table
    WHERE 1=1
        $filters
        AND $date_column BETWEEN '$start_date' AND '$end_date'
    GROUP BY 1
    ORDER BY value DESC
    """
)


TEMPLATES = {
    "trend": TREND_TEMPLATE,
    "summary": SUMMARY_TEMPLATE,
    "group_by": GROUP_BY_TEMPLATE,
}

__all__ = ["TEMPLATES"]
