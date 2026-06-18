from __future__ import annotations

from pathlib import Path

import click
import matplotlib.pyplot as plt
import seaborn as sns

from gqm_matrix.matrix import GQMMatrix
from gqm_matrix.models import Goal, Metric, Question


def sample_matrix() -> GQMMatrix:
    matrix = GQMMatrix()
    matrix.add_goal(
        Goal(
            id="G1",
            purpose="Improve software quality",
            object="Codebase",
            issue="Defect rate",
            viewpoint="Developer",
        )
    )
    matrix.add_question(
        Question(id="Q1", goal_id="G1", text="How many defects are found per release?")
    )
    matrix.add_question(
        Question(id="Q2", goal_id="G1", text="How quickly are defects resolved?")
    )
    matrix.add_metric(
        Metric(
            id="M1",
            question_id="Q1",
            name="Defects per release",
            unit="count",
            data_source="Issue tracker",
            baseline=12.0,
            target=6.0,
        )
    )
    matrix.add_metric(
        Metric(
            id="M2",
            question_id="Q2",
            name="Mean time to resolve",
            unit="hours",
            data_source="Issue tracker",
            baseline=48.0,
            target=24.0,
        )
    )
    return matrix


@click.group()
def main() -> None:
    """GQM matrix CLI."""


@main.command()
@click.option("--output", "-o", default="gqm_matrix.xlsx", help="Excel output path.")
@click.option("--plot", "-p", default="gqm_heatmap.png", help="Heatmap output path.")
def build(output: str, plot: str) -> None:
    """Build a sample GQM matrix and export results."""
    matrix = sample_matrix()

    excel_path = matrix.export_excel(output)
    click.echo(f"Exported Excel: {excel_path}")

    trace_df = matrix.traceability_matrix()
    plt.figure(figsize=(6, 4))
    sns.heatmap(trace_df, annot=True, cmap="Blues", cbar=False, linewidths=0.5)
    plt.title("GQM Traceability Matrix")
    plt.xlabel("Metrics")
    plt.ylabel("Goals")
    plt.tight_layout()

    plot_path = Path(plot)
    plt.savefig(plot_path, dpi=150)
    plt.close()
    click.echo(f"Saved heatmap: {plot_path}")


if __name__ == "__main__":
    main()
