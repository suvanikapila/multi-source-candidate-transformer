"""
pipeline.py — Main pipeline orchestrator.

Wires together: Ingest → Normalize → Merge → Confidence → Project → Validate → Emit

Usage:
    from pipeline.pipeline import run
    result = run(csv=..., ats=..., resume=..., notes=..., config=None)
"""

import json
import logging
import sys
from typing import Optional

from pipeline.ingest import csv_ingester, ats_ingester, resume_ingester, notes_ingester
from pipeline.merge import merge
from pipeline.confidence import compute_confidence
from pipeline.project import project
from pipeline.validate import validate

logger = logging.getLogger(__name__)


def run(
    csv:    Optional[str] = None,
    ats:    Optional[str] = None,
    resume: Optional[str] = None,
    notes:  Optional[str] = None,
    config: Optional[dict] = None,
    output_file: Optional[str] = None,
    verbose: bool = False,
) -> dict:
    """
    Execute the full pipeline end-to-end.

    Args:
        csv:         Path to recruiter CSV file (structured source).
        ats:         Path to ATS JSON blob (structured source).
        resume:      Path to resume PDF/DOCX/TXT (unstructured source).
        notes:       Path to recruiter notes .txt (unstructured source).
        config:      Runtime output config dict (None = default schema).
        output_file: If set, write JSON output to this path.
        verbose:     If True, log at DEBUG level.

    Returns:
        The final projected output dict.
    """
    if verbose:
        logging.basicConfig(
            level=logging.DEBUG,
            format="%(levelname)s | %(name)s | %(message)s",
            stream=sys.stderr,
        )
    else:
        logging.basicConfig(
            level=logging.INFO,
            format="%(levelname)s | %(message)s",
            stream=sys.stderr,
        )

    logger.info("=== Pipeline start ===")
    logger.info("Sources: csv=%s | ats=%s | resume=%s | notes=%s", csv, ats, resume, notes)

    # ── Stage 1: Ingest ────────────────────────────────────────────────────────
    records = []

    if csv:
        logger.info("[Ingest] CSV ← %s", csv)
        r = csv_ingester.ingest(csv)
        if r:
            records.append(r)
            logger.info("[Ingest] CSV: OK  (fields: %s)", list(r["fields"].keys()))
        else:
            logger.warning("[Ingest] CSV: no record returned — skipping.")

    if ats:
        logger.info("[Ingest] ATS ← %s", ats)
        r = ats_ingester.ingest(ats)
        if r:
            records.append(r)
            logger.info("[Ingest] ATS: OK  (fields: %s)", list(r["fields"].keys()))
        else:
            logger.warning("[Ingest] ATS: no record returned — skipping.")

    if resume:
        logger.info("[Ingest] Resume ← %s", resume)
        r = resume_ingester.ingest(resume)
        if r:
            records.append(r)
            logger.info("[Ingest] Resume: OK  (fields: %s)", list(r["fields"].keys()))
        else:
            logger.warning("[Ingest] Resume: no record returned — skipping.")

    if notes:
        logger.info("[Ingest] Notes ← %s", notes)
        r = notes_ingester.ingest(notes)
        if r:
            records.append(r)
            logger.info("[Ingest] Notes: OK  (fields: %s)", list(r["fields"].keys()))
        else:
            logger.warning("[Ingest] Notes: no record returned — skipping.")

    if not records:
        logger.error("Pipeline: no valid records from any source. Returning empty profile.")
        return {"error": "No valid source records ingested.", "candidate_id": None}

    logger.info("[Ingest] %d source(s) ingested successfully.", len(records))

    # ── Stage 2: Merge / Conflict-resolve ─────────────────────────────────────
    logger.info("[Merge] Resolving conflicts across %d source(s)...", len(records))
    canonical = merge(records)
    logger.info("[Merge] Canonical record built. candidate_id=%s", canonical.get("candidate_id"))

    # ── Stage 3: Confidence ───────────────────────────────────────────────────
    logger.info("[Confidence] Computing scores...")
    canonical = compute_confidence(canonical, records)
    logger.info("[Confidence] overall_confidence=%.4f", canonical.get("overall_confidence", 0))

    # ── Stage 4: Project ──────────────────────────────────────────────────────
    logger.info("[Project] Applying output config (custom=%s)...", bool(config and config.get("fields")))
    output = project(canonical, config)

    # ── Stage 5: Validate ─────────────────────────────────────────────────────
    logger.info("[Validate] Checking output against schema...")
    errors = validate(output, config)
    if errors:
        logger.warning("[Validate] Schema validation FAILED (%d error(s)):", len(errors))
        for e in errors:
            logger.warning("  • %s", e)
    else:
        logger.info("[Validate] Output is schema-valid. ✓")

    # ── Stage 6: Emit ─────────────────────────────────────────────────────────
    if output_file:
        try:
            with open(output_file, "w", encoding="utf-8") as f:
                json.dump(output, f, indent=2, ensure_ascii=False)
            logger.info("[Emit] Written to %s", output_file)
        except Exception as exc:
            logger.error("[Emit] Failed to write output file: %s", exc)

    logger.info("=== Pipeline complete ===")
    return output
