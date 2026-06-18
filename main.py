"""Entry point: import all project dependencies and run a quick sanity check."""

from __future__ import annotations

import json
import sys
from importlib.metadata import version

import click
import matplotlib
import numpy as np
import pandas as pd
import pydantic
import seaborn as sns
from dotenv import load_dotenv

from gqm_matrix import GQMMatrix, Goal, Metric, Question

DEPENDENCIES = {
    "numpy": np.__version__,
    "pandas": pd.__version__,
    "matplotlib": matplotlib.__version__,
    "seaborn": sns.__version__,
    "pydantic": pydantic.__version__,
    "click": version("click"),
    "python-dotenv": version("python-dotenv"),
    "openpyxl": version("openpyxl"),
}


def verify_imports() -> None:
    load_dotenv()
    print("All dependencies imported successfully:")
    for name, version in DEPENDENCIES.items():
        print(f"  - {name}: {version}")


def demo() -> None:
    matrix = GQMMatrix()
    matrix.add_goal(
        Goal(
            id="G1",
            purpose="Reduce lead time",
            object="CI/CD pipeline",
            issue="Cycle time",
            viewpoint="Engineering",
        )
    )
    matrix.add_question(
        Question(id="Q1", goal_id="G1", text="Which stages contribute most to wait time?")
    )
    matrix.add_metric(
        Metric(
            id="M1",
            question_id="Q1",
            name="Median cycle time per stage",
            unit="minutes",
            data_source="CI traces",
            baseline=45.0,
            target=30.0,
        )
    )

    hierarchy = matrix.to_dataframe()
    trace = matrix.traceability_matrix()

    print("\nGQM hierarchy:")
    print(hierarchy.to_string(index=False))
    print("\nTraceability matrix:")
    print(trace.to_string())

    summary = {
        "goals": len(matrix.goals),
        "questions": len(matrix.questions),
        "metrics": len(matrix.metrics),
    }
    print("\nSummary:", json.dumps(summary))


if __name__ == "__main__":
    verify_imports()
    demo()
    sys.exit(0)
