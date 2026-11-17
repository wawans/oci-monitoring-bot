"""On-demand CPU utilization chart generator using headless Matplotlib."""

import io
import logging
from datetime import datetime
from typing import List, Tuple

import matplotlib
matplotlib.use("Agg")  # Enforce headless rendering
import matplotlib.dates as mdates
import matplotlib.pyplot as plt

logger = logging.getLogger(__name__)


def generate_cpu_chart(
    datapoints: List[Tuple[datetime, float]],
    instance_name: str,
    hours: int = 24,
) -> io.BytesIO:
    """Generate a clean time-series line chart of CPU utilization as a PNG BytesIO buffer.

    Args:
        datapoints: List of (datetime, cpu_percent) tuples sorted chronologically.
        instance_name: Friendly display name of compute instance.
        hours: Query lookback window in hours.

    Returns:
        BytesIO object containing PNG image data ready to send via Telegram.
    """
    fig, ax = plt.subplots(figsize=(8, 4.5), dpi=120)

    # Styling colors
    fig.patch.set_facecolor("#1e1e2e")
    ax.set_facecolor("#181825")

    # Grid styling
    ax.grid(True, linestyle="--", alpha=0.3, color="#6c7086")

    # Labels and Titles
    ax.set_title(
        f"Grafik Utilisasi CPU: {instance_name} (Histori {hours} Jam)",
        fontsize=13,
        fontweight="bold",
        color="#cdd6f4",
        pad=12,
    )
    ax.set_ylabel("Utilisasi CPU (%)", fontsize=10, color="#a6adc8")
    ax.set_xlabel("Waktu (UTC)", fontsize=10, color="#a6adc8")
    ax.set_ylim(-2, 105)

    # Red dashed threshold line at 85% (Silent Watchdog Alert Threshold)
    ax.axhline(
        y=85,
        color="#f38ba8",
        linestyle="--",
        linewidth=1.5,
        alpha=0.8,
        label="Ambang Batas Alert (85%)",
    )

    if datapoints:
        timestamps, values = zip(*datapoints)
        ax.plot(
            timestamps,
            values,
            color="#89b4fa",
            linewidth=2.0,
            marker="o",
            markersize=3,
            label="CPU %",
        )
        # Fill under curve
        ax.fill_between(timestamps, values, color="#89b4fa", alpha=0.15)

        # X-axis time formatting
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
        fig.autofmt_xdate(rotation=30, ha="right")
    else:
        # No data placeholder
        ax.text(
            0.5,
            0.5,
            "Belum ada data telemetri CPU untuk periode ini",
            transform=ax.transAxes,
            fontsize=11,
            ha="center",
            va="center",
            color="#f38ba8",
        )

    # Axis tick colors
    ax.tick_params(colors="#a6adc8", which="both")
    for spine in ax.spines.values():
        spine.set_color("#45475a")

    ax.legend(facecolor="#1e1e2e", edgecolor="#45475a", labelcolor="#cdd6f4", loc="upper left")

    plt.tight_layout()

    buffer = io.BytesIO()
    fig.savefig(buffer, format="png", facecolor=fig.get_facecolor(), edgecolor="none")
    buffer.seek(0)
    plt.close(fig)

    logger.debug("Rendered CPU chart for %s with %d points", instance_name, len(datapoints))
    return buffer
