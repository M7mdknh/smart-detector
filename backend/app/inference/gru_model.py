"""Physics-informed residual GRU architecture, per sensor-risk-modeling's
model-specification.md: one GRU layer, hidden size 32, linear head producing
12 residual corrections. Predicts the residual against the cutoff-anchored
physics forecast, never an unconstrained absolute concentration:

    combined_forecast = physics_forecast + gru_residual_correction
"""

import torch
from torch import nn

from app.inference.gru_dataset import FEATURE_NAMES, INPUT_STEPS, OUTPUT_STEPS

HIDDEN_SIZE = 32


class ResidualGRU(nn.Module):
    def __init__(self, input_size: int = len(FEATURE_NAMES), hidden_size: int = HIDDEN_SIZE, output_size: int = OUTPUT_STEPS):
        super().__init__()
        self.gru = nn.GRU(input_size=input_size, hidden_size=hidden_size, num_layers=1, batch_first=True, dropout=0.0)
        self.head = nn.Linear(hidden_size, output_size)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        # x: (batch, INPUT_STEPS, input_size)
        _, h_n = self.gru(x)  # h_n: (1, batch, hidden_size)
        return self.head(h_n.squeeze(0))  # (batch, OUTPUT_STEPS)


def expected_input_shape() -> tuple[int, int]:
    return INPUT_STEPS, len(FEATURE_NAMES)
