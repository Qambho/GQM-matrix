from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from gqm_matrix.models import Goal, Metric, Question


class GQMMatrix:
    """Build and export a traceability matrix linking goals, questions, and metrics."""

    def __init__(self) -> None:
        self.goals: list[Goal] = []
        self.questions: list[Question] = []
        self.metrics: list[Metric] = []

    def add_goal(self, goal: Goal) -> None:
        self.goals.append(goal)

    def add_question(self, question: Question) -> None:
        self.questions.append(question)

    def add_metric(self, metric: Metric) -> None:
        self.metrics.append(metric)

    def to_dataframe(self) -> pd.DataFrame:
        rows: list[dict[str, object]] = []

        for goal in self.goals:
            goal_questions = [q for q in self.questions if q.goal_id == goal.id]
            if not goal_questions:
                rows.append(
                    {
                        "goal_id": goal.id,
                        "goal_purpose": goal.purpose,
                        "question_id": None,
                        "question_text": None,
                        "metric_id": None,
                        "metric_name": None,
                    }
                )
                continue

            for question in goal_questions:
                question_metrics = [m for m in self.metrics if m.question_id == question.id]
                if not question_metrics:
                    rows.append(
                        {
                            "goal_id": goal.id,
                            "goal_purpose": goal.purpose,
                            "question_id": question.id,
                            "question_text": question.text,
                            "metric_id": None,
                            "metric_name": None,
                        }
                    )
                    continue

                for metric in question_metrics:
                    rows.append(
                        {
                            "goal_id": goal.id,
                            "goal_purpose": goal.purpose,
                            "question_id": question.id,
                            "question_text": question.text,
                            "metric_id": metric.id,
                            "metric_name": metric.name,
                            "metric_unit": metric.unit,
                            "data_source": metric.data_source,
                            "baseline": metric.baseline,
                            "target": metric.target,
                        }
                    )

        return pd.DataFrame(rows)

    def traceability_matrix(self) -> pd.DataFrame:
        """Return a goal × metric binary matrix showing traceability links."""
        goal_ids = [g.id for g in self.goals]
        metric_ids = [m.id for m in self.metrics]
        matrix = np.zeros((len(goal_ids), len(metric_ids)), dtype=int)

        goal_index = {gid: idx for idx, gid in enumerate(goal_ids)}
        metric_index = {mid: idx for idx, mid in enumerate(metric_ids)}

        for question in self.questions:
            if question.goal_id not in goal_index:
                continue
            g_row = goal_index[question.goal_id]
            for metric in self.metrics:
                if metric.question_id == question.id and metric.id in metric_index:
                    matrix[g_row, metric_index[metric.id]] = 1

        return pd.DataFrame(matrix, index=goal_ids, columns=metric_ids)

    def export_excel(self, path: str | Path) -> Path:
        output = Path(path)
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            self.to_dataframe().to_excel(writer, sheet_name="GQM Hierarchy", index=False)
            self.traceability_matrix().to_excel(writer, sheet_name="Traceability Matrix")
        return output
