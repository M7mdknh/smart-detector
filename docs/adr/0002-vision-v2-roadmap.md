# ADR 0002: Vision v2.0 roadmap (deferred, not executed)

Status: **PARTIALLY EXECUTED, CANDIDATE REJECTED**. A later session had GPU
access (NVIDIA MX450) and Roboflow credentials, and did execute §2's dataset
acquisition (the "Industrial Safety" dataset only, MIT license) and §1's
single-stage retraining (not the two-stage architecture proposed below) as a
genuine experiment. See "Update — v1.2 experiment executed and rejected"
below for what actually happened. §3 (continuous interview video) remains
unexecuted as of that same session — see `demo-assets/INTERVIEW_VIDEO_SOURCES.md`.
The shipped detector remains `ppe-yolo11n.pt` (registry version 1.1); no
promotion occurred.

## Update — v1.2 experiment executed and rejected (see models/registry.json `ppe_detector.rejected_experiments`)

A fine-tuning run was started from the v1.1 checkpoint on the Industrial
Safety dataset (Roboflow Universe, MIT license; see
`models/evaluation/vision_v1.2_dataset_manifest.json` for the full
acquisition/leakage-check/subset-selection record), targeting 50 epochs. It
was externally interrupted after 7 completed epochs because the projected
MX450 runtime was unacceptable — this was **not** early stopping (no
patience/plateau criterion fired), and 50 epochs were never claimed complete.
The un-resumed, 7-epoch checkpoint was evaluated as an explicit early
candidate (`models/artifacts/ppe-yolo11n-v1.2-epoch7-candidate.pt`) via:

1. Validation-only threshold tuning (`models/evaluation/vision_v1.2_candidate_thresholds.json`).
2. A comparative evaluation against active v1.1 on 4 sources — the original
   construction-ppe test split, the Industrial-Safety dataset's own held-out
   test split, and both bundled video clips
   (`models/evaluation/vision_v1.2_comparative_evaluation.json`).
3. A mechanical promotion gate (`backend/scripts/promote_vision_v1_2.py`,
   `models/evaluation/vision_v1.2_promotion_decision.json`).

**Result: REJECTED.** The candidate's `no_helmet` recall on the construction-ppe
test split (0.25) did not improve over v1.1's own recall on that split (0.45),
and person/helmet recall on that same split collapsed (0.81→0.0, 0.90→0.10) —
expected for a detector trained only 7 of 50 planned epochs on a different
dataset. No further training was performed (explicitly out of scope for that
session). `models/registry.json`'s `ppe_detector` fields were never modified;
v1.1 remains active. This result does not retire the two-stage proposal in §1
below or the remaining datasets in §2 — it only closes out one single-stage,
partial-training experiment on one of the four named datasets.

## Original document (as written before the above update)

Nothing below this line was executed as of the original ADR. This ADR is a
specification for a future contributor who has the things this sandbox did
not have at the time: a GPU, Roboflow/Kaggle/HuggingFace credentials, and
legal authority to clear video licensing. It supersedes any notion that these
items were completed as part of the `assessment-submission-v2.0` release —
that release shipped only the restricted-zone rule, incident evidence images,
the clean-environment dependency/test fix, the duplicate-weight cleanup, and
the dataset tooling scaffold described in §4 below. No new YOLO model was
trained, compared, or promoted in that session; the shipped detector remained
`ppe-yolo11n.pt` (registry version 1.1, unchanged from
`assessment-submission-v1.0`).

## Context

The original ask for this pass was a "vision-enhanced v2.0": a two-stage
person-detector + PPE-detector architecture, ~8 externally sourced PPE
datasets, retraining/benchmarking YOLO11n/11s candidates, a licensed
continuous "interview" video for demo purposes, and a tagged release. None of
that is executable in this sandbox:

- **No GPU** (`nvidia-smi` absent) — a from-scratch or resumed multi-dataset
  YOLO11 training run is not practical here in reasonable time on CPU.
- **Roboflow/Kaggle/HuggingFace require account credentials to download**,
  which conflicts with CLAUDE.md's credential-free dataset requirement for
  anything `make demo`/`make train-vision` depends on, and an agent cannot
  create or hold those credentials on the user's behalf.
- **Video licensing cannot be legally verified by an AI agent.** Confirming
  that a specific piece of continuous footage is genuinely licensed for this
  use requires a human to check the actual source terms and, in most cases,
  accept a license or attribution obligation personally.

Per the user's explicit scope-down decision, this session built only the
*tooling* to prepare/audit/leak-check datasets once a human has them, plus
this roadmap document. It did not download, inspect, license, deduplicate, or
train on any of the datasets named below.

## 1. Two-stage architecture proposal

**Problem this would solve:** every candidate PPE dataset surveyed below
annotates `person` (or an equivalent full-body box) inconsistently — different
box conventions (tight vs. loose crop), different minimum-person-size
thresholds, and in at least one case no person class at all (PPE-item-only
annotations). Mixing them into one single-stage YOLO11 `person + helmet +
vest + no_helmet` model, as done for v1.0/v1.1, means the `person` class's
label quality is capped by whichever dataset contributes it, even for
images from a different, better-annotated dataset.

**Proposed architecture:**

1. **Stage 1 — person detector.** A YOLO11n (or 11s) model trained/fine-tuned
   on person-only annotations pooled from datasets with reliable person
   boxes (COCO-pretrained base, optionally fine-tuned further on the
   industrial/construction-scene subset for domain adaptation).
2. **Stage 2 — PPE-item detector.** A second YOLO11n model trained only on
   `helmet` / `vest` / `no_helmet` (and any other retained PPE classes),
   cropped/conditioned on stage-1 person boxes at inference time, so its
   label quality is not diluted by inconsistent person annotations from PPE-only
   datasets.
3. Association logic (bounding-box region assignment, dwell, zone membership)
   stays exactly as implemented in `backend/app/inference/ppe_association.py`
   and `backend/app/inference/vision_worker_impl.py` — only the detector
   stage changes, not the runtime pipeline architecture.

**Cost of NOT doing this (v1.1, current):** single-stage training pools all
annotations together; `no_helmet` recall is the known weak point (see
`models/registry.json`'s `test_set_comparison_v1.0_to_v1.1`, `no_helmet_recall`
0.125 → 0.175) — plausibly a person-box/PPE-box inconsistency problem, not
purely a data-volume problem. A two-stage design isolates that variable but
requires a from-scratch benchmark against the current single-stage baseline on
the same held-out test split before any promotion decision, per CLAUDE.md's
"Do not silently replace these choices" requirement.

## 2. Named external datasets — proposed, NOT acquired

None of the following were downloaded, inspected, license-verified,
deduplicated, or trained on in this session. Each entry is this ADR's
proposed canonical class mapping for a future contributor to verify against
the dataset's actual label file the first time they open it — the mapping
below is a plan, not a confirmed fact about dataset contents.

| Dataset | Source | Proposed canonical mapping | Status |
|---|---|---|---|
| Industrial Safety | Roboflow Universe | `person→person`, `hardhat→helmet`, `no-hardhat→no_helmet`, `vest→vest` | Not acquired |
| Safety-Helmet-Detection | Roboflow Universe | `head→no_helmet` (if no separate "wearing helmet" class exists, verify before mapping), `helmet→helmet` | Not acquired |
| PPE-detection | Roboflow Universe | `person→person`, `helmet→helmet`, `no-helmet→no_helmet`, `vest→vest`, other PPE classes (goggles/gloves/boots) dropped at runtime filter, same as v1.0/v1.1 | Not acquired |
| Hard-Hat-Worker-Safety-Equipments | Roboflow Universe | `hardhat→helmet`, `no-hardhat→no_helmet`, `person→person` if present | Not acquired |
| 4 additional "conditional" datasets (named by the user in the original request, exact identifiers not independently re-verified in this session) | Various (Roboflow/Kaggle) | To be mapped once inspected — do not assume class parity with the above without checking the actual label file | Not acquired; conditional on the primary 4 proving insufficient for the two-stage benchmark |
| 1 excluded HuggingFace dataset | HuggingFace Hub | N/A | Excluded per the original scoping conversation (reason not independently re-litigated here); listed for completeness only |

**Before any of these are used for training**, a future contributor must, per
CLAUDE.md and this project's existing evaluation discipline:

1. Download each dataset manually (with their own credentials) into a local
   directory.
2. Run `make prepare-vision-data --input-dir <dir>` (see §4) to generate a
   manifest per dataset (name, owner, url, license, version, download date,
   archive sha256, image/annotation counts, class list) and apply the
   canonical class-name normalization.
3. Verify the actual license terms permit this use (train a model, ship
   weights, redistribute in an assessment submission) — Roboflow Universe
   datasets carry per-dataset licenses (CC BY 4.0, CC BY-SA, etc.) that must
   be checked individually and recorded in the manifest, not assumed.
4. Run `make audit-vision-data` (exact/near-duplicate detection, class
   balance, missing/corrupt annotation checks) across the pooled manifests.
5. Assign train/val/test splits and run `make check-vision-leakage` to prove
   no duplicate/near-duplicate/same-scene image crosses a split boundary —
   the same discipline already applied to the GRU forecast model
   (`models/evaluation/gru_leakage_proof.json`).
6. Only then train the two-stage candidates and benchmark them against the
   current v1.1 single-stage baseline on the same held-out test split,
   producing a benchmark report analogous to
   `models/evaluation/gru_benchmark_report.json` before any promotion decision.

## 3. Continuous "interview compilation" video — NOT acquired

The demo currently uses `demo-assets/replay.mp4`, a slideshow of distinct
licensed still images (see `demo-assets/REPLAY_SOURCE.md`), not one
continuous factory-floor shot. The original request wanted a genuine
continuous "interview compilation" clip so the replay path exercises
sustained multi-frame tracking (ByteTrack identity persistence, PPE dwell
over a real continuous scene) rather than jump-cutting between stills.

**No such licensed footage was acquired or fabricated in this session.** A
future contributor adding it must:

1. **Source selection criteria:** continuous, single-take (or minimally cut)
   footage of a person in an industrial/construction-like setting, at least
   60–120 seconds, with visible variation in helmet/vest compliance if
   possible (to exercise both COMPLIANT and NON_COMPLIANT dwell paths).
2. **License verification checklist:** confirm the exact license (public
   domain, CC0, CC BY, or an explicit stock-footage license that permits
   redistribution inside a shipped repository/archive); record the license
   text/URL and access date in a new `demo-assets/INTERVIEW_VIDEO_SOURCES.md`
   file, following the same pattern as `demo-assets/REPLAY_SOURCE.md` and
   `demo-assets/NATURAL_MOTION_SOURCE.md`; do not use footage whose license
   is ambiguous or requires an attribution the project cannot practically give.
3. **Expected file paths/format** once acquired:
   - `demo-assets/interview_compilation_source.mp4` — the raw sourced clip.
   - `demo-assets/interview_compilation_source_annotated.mp4` — the same clip
     run through the real YOLO11n + ByteTrack pipeline with boxes/track
     IDs/PPE state burned in, generated the same way
     `backend/scripts/build_replay_clip.py` produces the existing bundled
     replay's annotated variants.
   - `demo-assets/INTERVIEW_VIDEO_SOURCES.md` — license/source/access-date
     record for the new clip, in the same format as the existing
     `*_SOURCE.md` files.
4. Once present, `make interview-demo` (see `docs/INTERVIEW_DEMO.md`) will run
   the sequence end-to-end against it. Until then, `make interview-demo`
   correctly and intentionally refuses to run (see that target's guard logic
   in the `Makefile`) rather than faking a slideshow demo as if it were
   continuous video.

## 4. Dataset preparation tooling contract (implemented, input-less until real data arrives)

`backend/scripts/vision_data/prepare_vision_data.py`,
`audit_vision_data.py`, and `check_vision_leakage.py` (wired to `make
prepare-vision-data`, `make audit-vision-data`, `make check-vision-leakage`)
implement the manifest/audit/leakage-check logic described in §2 above. They
are exercised today only against synthetic placeholder fixtures under
`backend/tests/fixtures/vision_data_sample/` (see
`backend/tests/test_vision_data_tooling.py`) — this proves the tooling's
*logic* is correct, not that any real external dataset has been validated.
When no `--input-dir` is given (or it is empty, which will always be true
until a human adds real dataset archives), `prepare_vision_data.py` prints a
clear "nothing to prepare" message and exits 0 rather than failing, since
there is genuinely nothing to prepare yet in this sandbox.

## Decision

Ship `assessment-submission-v2.0` with only the genuinely executable subset
(restricted-zone rule, incident evidence images, lean/vision dependency and
test-target separation, duplicate-weight cleanup, and this tooling/ADR pair).
Treat everything in §1–§3 as a specification for future work, to be picked up
by a contributor with GPU access, dataset credentials, and legal review
authority — not as a task this session could or did complete.
