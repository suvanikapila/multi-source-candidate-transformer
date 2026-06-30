# Multi-Source Candidate Data Transformer

**Eightfold Engineering Intern (Jul–Dec 2026) — Stage 2 Implementation**
*Suvani Kapila | kapilasuvani@gmail.com*

---

## Demo

▶️ [**Watch the demo video**](demo/demo.mp4)

> The demo walks through the full pipeline: passing all four source types via the CLI, verbose logging output, the produced canonical JSON, and custom config projection.

---

## What It Does

Ingests candidate information from multiple sources, normalizes all fields to canonical formats, merges/deduplicates across sources (with conflict resolution), assigns provenance and confidence, and emits a clean canonical JSON profile.

**Pipeline**: Ingest → Normalize → Merge → Confidence → Project → Validate → Emit

---

## Quickstart

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Run with default schema (all 4 sources)

```bash
python run.py \
  --csv data/sample_candidate.csv \
  --ats data/sample_ats.json \
  --resume data/sample_resume.txt \
  --notes data/sample_notes.txt
```

Output is printed to stdout (JSON). See `output/default_output.json` for pre-generated output.

### 3. Run with custom output config

```bash
python run.py \
  --csv data/sample_candidate.csv \
  --ats data/sample_ats.json \
  --config config/custom_config.json
```

See `output/custom_output.json` for pre-generated output.

### 4. Write output to a file

```bash
python run.py \
  --csv data/sample_candidate.csv \
  --ats data/sample_ats.json \
  --out output/my_result.json
```

### 5. Verbose / debug logging

```bash
python run.py --csv data/sample_candidate.csv --ats data/sample_ats.json -v
```

---

## CLI Options

| Flag | Description |
|------|-------------|
| `--csv FILE` | Recruiter CSV export (structured source) |
| `--ats FILE` | ATS JSON blob (structured source) |
| `--resume FILE` | Resume PDF/DOCX/TXT (unstructured source) |
| `--notes FILE` | Recruiter notes .txt (unstructured source) |
| `--config FILE` | Runtime output config JSON |
| `--out FILE` | Write JSON output to this file (default: stdout) |
| `-v` | Enable verbose/debug logging |

---

## Source Types Covered

| Group | Source | Format |
|-------|--------|--------|
| Structured | Recruiter CSV export | `.csv` |
| Structured | ATS JSON blob | `.json` (non-canonical field names) |
| Unstructured | Resume | `.pdf` / `.docx` / `.txt` |
| Unstructured | Recruiter notes | `.txt` (free text) |

> Any source may be missing, empty, or malformed — the pipeline **never crashes**. Missing/unreadable files are logged as warnings and the pipeline continues on remaining sources.

---

## Default Output Schema

```json
{
  "candidate_id":     "cand_<sha256-12>",
  "full_name":        "string",
  "emails":           ["string"],
  "phones":           ["string (E.164)"],
  "location":         { "city": "string", "region": "string", "country": "ISO-3166 alpha-2" },
  "links":            { "linkedin": "string", "github": "string", "portfolio": "string", "other": [] },
  "headline":         "string | null",
  "years_experience": "number | null",
  "skills":           [{ "name": "string", "confidence": 0.0–1.0, "sources": ["string"] }],
  "experience":       [{ "company": "string", "title": "string", "start": "YYYY-MM", "end": "YYYY-MM", "summary": "string" }],
  "education":        [{ "institution": "string", "degree": "string", "field": "string", "end_year": number }],
  "provenance":       [{ "field": "string", "source": "string", "method": "string" }],
  "overall_confidence": 0.0–1.0
}
```

---

## Runtime Config (Configurable Output)

The pipeline accepts a config that reshapes the output **without touching the engine**:

```json
{
  "fields": [
    { "path": "full_name",     "type": "string",   "required": true },
    { "path": "primary_email", "from": "emails[0]","type": "string",   "required": true },
    { "path": "phone",         "from": "phones[0]","type": "string",   "normalize": "E164" },
    { "path": "skills",        "from": "skills[].name", "type": "string[]", "normalize": "canonical" }
  ],
  "include_confidence": true,
  "on_missing": "null"
}
```

**Config capabilities:**
- `path` — output key name
- `from` — source path in canonical record (supports `field[0]`, `field[].key`, `field.subfield`)
- `normalize` — `"E164"` or `"canonical"` (skill normalization)
- `required` — combined with `on_missing: "error"` to enforce presence
- `on_missing` — `"null"` (include with null) | `"omit"` (exclude field) | `"error"` (raise)
- `include_confidence` — add `overall_confidence` and `provenance` to output

---

## Merge / Conflict Resolution Policy

Records are grouped by match key (normalized primary email → fallback: fuzzy name + phone).

For each field across matched records:
- **Winner** = highest `source_priority × extraction_confidence`
- **Tiebreak** = majority agreement
- All losing values stored in `provenance[]` — nothing silently discarded

| Source | Priority Weight |
|--------|----------------|
| CSV | 0.90 |
| ATS JSON | 0.85 |
| Resume | 0.75 |
| Recruiter notes | 0.60 |

---

## Edge Cases Handled

| Edge Case | Behavior |
|-----------|----------|
| Missing source file | Logged warning, pipeline continues |
| Malformed JSON / garbage CSV row | Field coerced to null, never invented |
| Conflicting values across sources | Resolved by priority×confidence; alternatives in provenance |
| Same candidate, name/casing variants | Deduplicated via normalized email match key |
| Unparsable/scanned PDF | Affected fields → null, overall_confidence lowered, no crash |
| Empty skill list | skills = [], no error |
| Ambiguous phone (no country code) | Attempts E.164 with default region, falls back to null |
| ATS with non-canonical field names | Mapped via ATS_FIELD_MAP, unknown keys ignored |

---

## Running Tests

```bash
pytest tests/ -v
```

Expected output: all tests pass.

---

## Project Structure

```
candidate-transformer/
├── pipeline/
│   ├── ingest/
│   │   ├── csv_ingester.py         # Recruiter CSV
│   │   ├── ats_ingester.py         # ATS JSON blob
│   │   ├── resume_ingester.py      # PDF/DOCX/TXT
│   │   └── notes_ingester.py       # Free text
│   ├── normalize/
│   │   ├── date_normalizer.py      # → YYYY-MM
│   │   ├── phone_normalizer.py     # → E.164
│   │   ├── location_normalizer.py  # → ISO-3166
│   │   └── skill_normalizer.py     # → canonical via dict + rapidfuzz
│   ├── merge.py                    # Conflict resolution + provenance
│   ├── confidence.py               # Per-field + overall scoring
│   ├── project.py                  # Runtime config projection
│   ├── validate.py                 # JSON Schema validation
│   └── pipeline.py                 # Orchestrator
├── schemas/canonical_schema.json   # JSON Schema for validation
├── config/
│   ├── default_config.json
│   └── custom_config.json
├── data/                           # Sample inputs
├── output/                         # Pre-generated outputs
├── tests/                          # Pytest test suite
├── skills_dictionary.txt           # Canonical skill names
├── run.py                          # CLI entrypoint
└── requirements.txt
```

---

## Design Notes

- **Canonical record is never mutated** — the projection layer is purely stateless
- **Deterministic by design** — `candidate_id` is SHA-256 of normalized email; same inputs → same output
- **Wrong-but-confident is worse than honestly-empty** — all unknown values → null, never invented
- **Skills** normalized via dictionary lookup + rapidfuzz fuzzy match (threshold 80); no live APIs
- **Live GitHub/LinkedIn APIs deliberately excluded** — avoids auth, rate-limits, and non-determinism
