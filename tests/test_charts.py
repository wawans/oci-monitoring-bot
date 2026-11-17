"""Unit tests for Matplotlib headless CPU chart generator."""

from datetime import datetime, timedelta, timezone

from src.bot.charts import generate_cpu_chart


class TestCpuChartGenerator:
    """Tests for time-series chart rendering and PNG buffer output."""

    def test_generate_chart_with_data(self) -> None:
        """Verify generating chart with time-series datapoints produces a valid PNG buffer."""
        now = datetime.now(timezone.utc)
        datapoints = [
            (now - timedelta(hours=3), 20.0),
            (now - timedelta(hours=2), 55.5),
            (now - timedelta(hours=1), 88.0),
            (now, 45.2),
        ]

        buffer = generate_cpu_chart(datapoints, "prod-api-server", hours=6)

        assert buffer is not None
        bytes_data = buffer.getvalue()
        # Verify valid PNG header magic number: \x89PNG\r\n\x1a\n
        assert bytes_data.startswith(b"\x89PNG\r\n\x1a\n")
        assert len(bytes_data) > 5000  # Valid PNG image size

    def test_generate_chart_empty_datapoints(self) -> None:
        """Verify generating chart with empty points generates valid placeholder PNG."""
        buffer = generate_cpu_chart([], "idle-server", hours=24)

        assert buffer is not None
        bytes_data = buffer.getvalue()
        assert bytes_data.startswith(b"\x89PNG\r\n\x1a\n")
        assert len(bytes_data) > 3000
