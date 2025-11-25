"""
Tests for chart/chart_builder.py - chart type inference and generation.
"""
import json
from pathlib import Path
import pytest

from chart.chart_builder import build_chart, _infer_chart_strategy


class TestChartInference:
    """Test chart type inference logic."""
    
    def test_summary_intent_infers_kpi(self):
        """Summary (no group_by) should infer KPI card."""
        intent = {"metric": "revenue", "group_by": None}
        results = [{"metric": 1000000}]
        strategy = _infer_chart_strategy(intent, results)
        assert strategy == "kpi"
    
    def test_trend_intent_infers_line(self):
        """Trend (group_by='month') should infer line chart."""
        intent = {"metric": "revenue", "group_by": "month"}
        results = [
            {"month": "2024-01", "metric": 100},
            {"month": "2024-02", "metric": 120},
        ]
        strategy = _infer_chart_strategy(intent, results)
        assert strategy == "line"
    
    def test_groupby_dimension_infers_bar(self):
        """Group by non-time dimension should infer bar chart."""
        intent = {"metric": "revenue", "group_by": "region"}
        results = [
            {"group_col": "APAC", "metric": 200},
            {"group_col": "EMEA", "metric": 150},
            {"group_col": "NA", "metric": 180},
        ]
        strategy = _infer_chart_strategy(intent, results)
        assert strategy == "bar"


class TestChartGeneration:
    """Test end-to-end chart generation."""
    
    def test_kpi_chart_generates_html(self, tmp_path):
        """KPI chart should generate valid HTML file."""
        intent = {"metric": "revenue", "group_by": None}
        results = [{"metric": 1000000}]
        output = tmp_path / "test_kpi.html"
        
        info = build_chart(intent, results, output_path=str(output), include_base64=False)
        
        assert info["chart_type"] == "kpi"
        assert Path(info["html_path"]).exists()
        html_content = Path(info["html_path"]).read_text()
        assert "plotly" in html_content.lower()
        assert "1000000" in html_content or "1,000,000" in html_content
    
    def test_line_chart_generates_html(self, tmp_path):
        """Line chart should generate valid HTML file."""
        intent = {"metric": "revenue", "group_by": "month"}
        results = [
            {"month": "2024-01", "metric": 100},
            {"month": "2024-02", "metric": 120},
            {"month": "2024-03", "metric": 110},
        ]
        output = tmp_path / "test_line.html"
        
        info = build_chart(intent, results, output_path=str(output), include_base64=False)
        
        assert info["chart_type"] == "line"
        assert Path(info["html_path"]).exists()
        html_content = Path(info["html_path"]).read_text()
        assert "plotly" in html_content.lower()
        assert "2024-01" in html_content
    
    def test_bar_chart_generates_html(self, tmp_path):
        """Bar chart should generate valid HTML file."""
        intent = {"metric": "revenue", "group_by": "region"}
        results = [
            {"group_col": "APAC", "metric": 200},
            {"group_col": "EMEA", "metric": 150},
        ]
        output = tmp_path / "test_bar.html"
        
        info = build_chart(intent, results, output_path=str(output), include_base64=False)
        
        assert info["chart_type"] == "bar"
        assert Path(info["html_path"]).exists()
        html_content = Path(info["html_path"]).read_text()
        assert "plotly" in html_content.lower()
        assert "APAC" in html_content
    
    def test_empty_results_returns_none(self, tmp_path):
        """Empty results should return chart_type='none'."""
        intent = {"metric": "revenue"}
        results = []
        
        info = build_chart(intent, results)
        
        assert info["chart_type"] == "none"
        assert info["html_path"] is None
    
    def test_base64_encoding_optional(self, tmp_path):
        """Base64 encoding should be optional."""
        intent = {"metric": "revenue", "group_by": None}
        results = [{"metric": 1000}]
        output = tmp_path / "test_base64.html"
        
        # Without base64
        info_no_b64 = build_chart(intent, results, output_path=str(output), include_base64=False)
        assert "html_base64" not in info_no_b64
        
        # With base64
        info_with_b64 = build_chart(intent, results, output_path=str(output), include_base64=True)
        assert "html_base64" in info_with_b64
        assert isinstance(info_with_b64["html_base64"], str)
        assert len(info_with_b64["html_base64"]) > 0


class TestChartIntegration:
    """Test chart generation with real query results."""
    
    def test_acceptance_summary_with_chart(self, tmp_path):
        """Summary query should generate KPI chart."""
        from nlp.llm_intent_parser import parse_intent_with_llm
        from validation.validator import validate_intent
        from builder.sql_builder import build_sql
        from sqlalchemy import create_engine
        
        config = json.loads(Path("config_store/tenant1.json").read_text(encoding="utf-8-sig"))
        question = "Total revenue from EMEA region for last 12 months"
        
        intent = parse_intent_with_llm(question, config)
        validated = validate_intent(intent, config)
        sel, params = build_sql(validated, config, db_type='sqlite')
        
        engine = create_engine('sqlite:///enhanced_sales.db')
        conn = engine.connect()
        res = conn.execute(sel, params)
        rows = [dict(r._mapping) for r in res]
        conn.close()
        
        output = tmp_path / "test_summary.html"
        info = build_chart(intent=validated, results=rows, output_path=str(output))
        
        assert info["chart_type"] == "kpi"
        assert Path(info["html_path"]).exists()
    
    def test_acceptance_trend_with_chart(self, tmp_path):
        """Trend query should generate line chart."""
        from nlp.llm_intent_parser import parse_intent_with_llm
        from validation.validator import validate_intent
        from builder.sql_builder import build_sql
        from sqlalchemy import create_engine
        
        config = json.loads(Path("config_store/tenant1.json").read_text(encoding="utf-8-sig"))
        question = "Revenue trend over last 12 months"
        
        intent = parse_intent_with_llm(question, config)
        validated = validate_intent(intent, config)
        sel, params = build_sql(validated, config, db_type='sqlite')
        
        engine = create_engine('sqlite:///enhanced_sales.db')
        conn = engine.connect()
        res = conn.execute(sel, params)
        rows = [dict(r._mapping) for r in res]
        conn.close()
        
        output = tmp_path / "test_trend.html"
        info = build_chart(intent=validated, results=rows, output_path=str(output))
        
        assert info["chart_type"] == "line"
        assert Path(info["html_path"]).exists()
        assert len(rows) > 1  # trend should have multiple data points
