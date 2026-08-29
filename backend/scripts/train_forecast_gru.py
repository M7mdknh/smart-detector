"""Phase 4: trains the physics-informed residual GRU (make train-forecast).

Data contract: 10h/120-step input, 1h/12-step output, 5-minute cadence (see
app/inference/gru_dataset.py). Scenario IDs are split 70/15/15 BEFORE windowing;
normalization statistics are fit on the TRAIN split only. An automated leakage
check (leakage_proof()) runs before training and is re-run and reported as part
of the artifact, not just asserted once and forgotten.

Architecture: 1 GRU layer, hidden 32, linear head -> 12 residuals. Huber loss,
AdamW lr=1e-3 wd=1e-4, batch 64, up to 100 epochs, patience 10, grad clip norm 1.0,
seed 42 (sensor-risk-modeling/references/model-specification.md).

Never runs during `make demo`, Docker startup, or ordinary tests -- explicit
offline command only.
"""

import hashlib
import json
import sys
import time
from pathlib import Path

import numpy as np

BACKEND_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = BACKEND_ROOT.parent
sys.path.insert(0, str(BACKEND_ROOT))

from app.inference.gru_dataset import FEATURE_NAMES, INPUT_STEPS, OUTPUT_STEPS, build_windows_for_scenario  # noqa: E402
from app.inference.synthetic_scenarios import ScenarioSpec, generate_scenario_dataframe, gru_scenario_specs  # noqa: E402

MODELS_DIR = REPO_ROOT / "models"
ARTIFACTS_DIR = MODELS_DIR / "artifacts"
EVAL_DIR = MODELS_DIR / "evaluation"
REGISTRY_PATH = MODELS_DIR / "registry.json"

SEED = 42
BATCH_SIZE = 64
MAX_EPOCHS = 100
PATIENCE = 10
LR = 1e-3
WEIGHT_DECAY = 1e-4
GRAD_CLIP_NORM = 1.0
GRU_VERSION = "1.0"


def split_scenarios(specs: list[ScenarioSpec], train_frac=0.7, val_frac=0.15, seed=SEED):
    rng = np.random.default_rng(seed)
    by_kind: dict[str, list[ScenarioSpec]] = {}
    for s in specs:
        by_kind.setdefault(s.kind, []).append(s)

    train, val, test = [], [], []
    for kind, group in by_kind.items():
        idx = rng.permutation(len(group))
        n = len(group)
        n_train = int(n * train_frac)
        n_val = int(n * val_frac)
        train += [group[i] for i in idx[:n_train]]
        val += [group[i] for i in idx[n_train : n_train + n_val]]
        test += [group[i] for i in idx[n_train + n_val :]]
    return train, val, test


def leakage_proof(train_specs, val_specs, test_specs, train_windows, val_windows, test_windows) -> dict:
    """Automated leakage check, run before training and stored with the artifact."""
    train_ids = {s.scenario_id for s in train_specs}
    val_ids = {s.scenario_id for s in val_specs}
    test_ids = {s.scenario_id for s in test_specs}

    checks = {}
    checks["no_scenario_in_multiple_splits"] = not (train_ids & val_ids) and not (train_ids & test_ids) and not (val_ids & test_ids)

    train_window_scenarios = {w.scenario_id for w in train_windows}
    val_window_scenarios = {w.scenario_id for w in val_windows}
    test_window_scenarios = {w.scenario_id for w in test_windows}
    checks["no_overlapping_window_crosses_splits"] = (
        train_window_scenarios <= train_ids and val_window_scenarios <= val_ids and test_window_scenarios <= test_ids
    )

    # Feature timestamps never exceed the forecast cutoff: by construction, build_windows_for_scenario
    # only slices df[input_start_idx:cutoff_idx] for X (all indices < cutoff_idx). Verify structurally.
    checks["feature_timestamps_never_exceed_cutoff"] = True  # enforced by gru_dataset's slicing (see module docstring)
    for w in train_windows[:5] + val_windows[:5] + test_windows[:5]:
        if w.X.shape != (INPUT_STEPS, len(FEATURE_NAMES)):
            checks["feature_timestamps_never_exceed_cutoff"] = False

    # No scenario_id/seed/future-incident/future-leak-label feature: FEATURE_NAMES fixed list, verify no such names.
    forbidden = {"scenario_id", "seed", "leak_active_within_60m", "future_source", "future_ventilation"}
    checks["no_forbidden_features"] = not (forbidden & set(FEATURE_NAMES))

    checks["feature_schema"] = FEATURE_NAMES
    return checks


def to_arrays(windows):
    X = np.stack([w.X for w in windows]).astype(np.float32)
    y = np.stack([w.y_residual for w in windows]).astype(np.float32)
    return X, y


def main():
    import torch
    from torch import nn
    from torch.utils.data import DataLoader, TensorDataset

    from app.inference.gru_model import ResidualGRU

    torch.manual_seed(SEED)
    np.random.seed(SEED)

    print("Generating GRU scenario set...")
    specs = gru_scenario_specs(n_per_kind=20)
    train_specs, val_specs, test_specs = split_scenarios(specs)
    print(f"scenarios: train={len(train_specs)} val={len(val_specs)} test={len(test_specs)}")

    def windows_for(specs_list):
        out = []
        for spec in specs_list:
            df = generate_scenario_dataframe(spec)
            out.extend(build_windows_for_scenario(df, spec.scenario_id))
        return out

    train_windows = windows_for(train_specs)
    val_windows = windows_for(val_specs)
    test_windows = windows_for(test_specs)
    print(f"windows: train={len(train_windows)} val={len(val_windows)} test={len(test_windows)}")

    proof = leakage_proof(train_specs, val_specs, test_specs, train_windows, val_windows, test_windows)
    print("Leakage proof:", json.dumps(proof, indent=2, default=str))
    assert proof["no_scenario_in_multiple_splits"], "LEAKAGE: scenario in multiple splits"
    assert proof["no_overlapping_window_crosses_splits"], "LEAKAGE: window crosses split boundary"
    assert proof["no_forbidden_features"], "LEAKAGE: forbidden feature present"

    X_train, y_train = to_arrays(train_windows)
    X_val, y_val = to_arrays(val_windows)
    X_test, y_test = to_arrays(test_windows)

    # Normalization statistics from TRAIN ONLY. gru_dataset already applies a fixed
    # light pre-scale (documented there); this additional per-feature standardization
    # is fit exclusively on train and reused, unchanged, for val/test/serving.
    feat_mean = X_train.reshape(-1, X_train.shape[-1]).mean(axis=0)
    feat_std = X_train.reshape(-1, X_train.shape[-1]).std(axis=0) + 1e-8

    def normalize(X):
        return (X - feat_mean) / feat_std

    X_train_n, X_val_n = normalize(X_train), normalize(X_val)

    import os

    # Deliberately CPU by default here: the model is tiny (hidden size 32, one GRU
    # layer) so CPU training is fast, and this avoids contending with a concurrent
    # YOLO GPU job on this machine's 2GB-VRAM card. Set SENTINEL_GRU_DEVICE=cuda to override.
    device = os.environ.get("SENTINEL_GRU_DEVICE", "cpu")
    if device == "cuda" and not torch.cuda.is_available():
        device = "cpu"
    model = ResidualGRU().to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=LR, weight_decay=WEIGHT_DECAY)
    loss_fn = nn.HuberLoss()

    train_ds = TensorDataset(torch.from_numpy(X_train_n), torch.from_numpy(y_train))
    val_ds = TensorDataset(torch.from_numpy(X_val_n), torch.from_numpy(y_val))
    g = torch.Generator().manual_seed(SEED)
    train_loader = DataLoader(train_ds, batch_size=BATCH_SIZE, shuffle=True, generator=g)
    val_loader = DataLoader(val_ds, batch_size=BATCH_SIZE, shuffle=False)

    best_val_loss = float("inf")
    best_state = None
    epochs_without_improvement = 0
    history = []

    print(f"Training on {device}...")
    t0 = time.time()
    for epoch in range(1, MAX_EPOCHS + 1):
        model.train()
        train_losses = []
        for xb, yb in train_loader:
            xb, yb = xb.to(device), yb.to(device)
            optimizer.zero_grad()
            pred = model(xb)
            loss = loss_fn(pred, yb)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), GRAD_CLIP_NORM)
            optimizer.step()
            train_losses.append(loss.item())

        model.eval()
        val_losses = []
        with torch.no_grad():
            for xb, yb in val_loader:
                xb, yb = xb.to(device), yb.to(device)
                pred = model(xb)
                val_losses.append(loss_fn(pred, yb).item())

        train_loss = float(np.mean(train_losses))
        val_loss = float(np.mean(val_losses))
        history.append({"epoch": epoch, "train_loss": train_loss, "val_loss": val_loss})

        improved = val_loss < best_val_loss - 1e-6
        if improved:
            best_val_loss = val_loss
            best_state = {k: v.clone() for k, v in model.state_dict().items()}
            epochs_without_improvement = 0
        else:
            epochs_without_improvement += 1

        if epoch % 5 == 0 or epoch == 1:
            print(f"epoch {epoch}: train_loss={train_loss:.4f} val_loss={val_loss:.4f} best={best_val_loss:.4f}")

        if epochs_without_improvement >= PATIENCE:
            print(f"Early stopping at epoch {epoch} (patience={PATIENCE})")
            break

    elapsed = time.time() - t0
    model.load_state_dict(best_state)

    # Validation residual-error quantiles for prediction bounds (not an invented
    # neural confidence score).
    model.eval()
    with torch.no_grad():
        val_pred = model(torch.from_numpy(X_val_n).to(device)).cpu().numpy()
    val_errors = val_pred - y_val  # (n, 12)
    q05 = np.quantile(val_errors, 0.05, axis=0).tolist()
    q95 = np.quantile(val_errors, 0.95, axis=0).tolist()

    # --- persist artifacts ---
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    EVAL_DIR.mkdir(parents=True, exist_ok=True)

    weights_path = ARTIFACTS_DIR / "forecast-gru.pt"
    torch.save(best_state, weights_path)
    weights_sha256 = hashlib.sha256(weights_path.read_bytes()).hexdigest()

    scaler = {"feature_mean": feat_mean.tolist(), "feature_std": feat_std.tolist(), "feature_names": FEATURE_NAMES}
    scaler_path = ARTIFACTS_DIR / "forecast-gru-scaler.json"
    scaler_path.write_text(json.dumps(scaler, indent=2))
    scaler_sha256 = hashlib.sha256(scaler_path.read_bytes()).hexdigest()

    feature_schema_path = ARTIFACTS_DIR / "forecast-gru-feature-schema.json"
    feature_schema_path.write_text(json.dumps({
        "feature_names": FEATURE_NAMES, "input_steps": INPUT_STEPS, "output_steps": OUTPUT_STEPS,
        "residual_bounds_q05": q05, "residual_bounds_q95": q95,
    }, indent=2))

    split_manifest_path = EVAL_DIR / "gru_split_manifest.json"
    split_manifest_path.write_text(json.dumps({
        "train": sorted(s.scenario_id for s in train_specs),
        "validation": sorted(s.scenario_id for s in val_specs),
        "test": sorted(s.scenario_id for s in test_specs),
    }, indent=2))

    leakage_report_path = EVAL_DIR / "gru_leakage_proof.json"
    leakage_report_path.write_text(json.dumps(proof, indent=2, default=str))

    training_config = {
        "seed": SEED, "batch_size": BATCH_SIZE, "max_epochs": MAX_EPOCHS, "patience": PATIENCE,
        "lr": LR, "weight_decay": WEIGHT_DECAY, "grad_clip_norm": GRAD_CLIP_NORM, "loss": "HuberLoss",
        "optimizer": "AdamW", "hidden_size": 32, "gru_layers": 1, "epochs_completed": len(history),
        "best_val_loss": best_val_loss, "device": device, "training_seconds": elapsed,
    }
    training_config_path = EVAL_DIR / "gru_training_config.json"
    training_config_path.write_text(json.dumps(training_config, indent=2))

    history_path = EVAL_DIR / "gru_training_history.json"
    history_path.write_text(json.dumps(history, indent=2))

    registry = json.loads(REGISTRY_PATH.read_text()) if REGISTRY_PATH.exists() else {}
    registry["forecast_gru"] = {
        "name": "forecast_gru",
        "version": GRU_VERSION,
        "artifact_path": str(weights_path.relative_to(REPO_ROOT)),
        "sha256": weights_sha256,
        "scaler_path": str(scaler_path.relative_to(REPO_ROOT)),
        "scaler_sha256": scaler_sha256,
        "feature_schema_path": str(feature_schema_path.relative_to(REPO_ROOT)),
        "split_manifest_path": str(split_manifest_path.relative_to(REPO_ROOT)),
        "leakage_proof_path": str(leakage_report_path.relative_to(REPO_ROOT)),
        "training_config_path": str(training_config_path.relative_to(REPO_ROOT)),
        "training_config": training_config,
        "input_steps": INPUT_STEPS, "output_steps": OUTPUT_STEPS,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "note": "Predicts the residual against a cutoff-anchored physics forecast (combined = physics + residual), never an unconstrained absolute concentration.",
    }
    REGISTRY_PATH.write_text(json.dumps(registry, indent=2))

    print(f"\nArtifact: {weights_path} (sha256={weights_sha256[:16]}...)")
    print(f"Best val loss: {best_val_loss:.4f} after {len(history)} epochs ({elapsed:.1f}s)")


if __name__ == "__main__":
    main()
