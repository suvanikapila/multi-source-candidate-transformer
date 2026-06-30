#!/usr/bin/env python3
"""
run.py — CLI entrypoint for the Multi-Source Candidate Data Transformer.

Usage:
  python run.py --csv data/sample_candidate.csv --ats data/sample_ats.json \
                --resume data/sample_resume.txt --notes data/sample_notes.txt

  # With custom config:
  python run.py --csv data/sample_candidate.csv --ats data/sample_ats.json \
                --config config/custom_config.json

  # Write output to file:
  python run.py --csv data/sample_candidate.csv --ats data/sample_ats.json \
                --out output/result.json

  # Verbose logging:
  python run.py --csv data/sample_candidate.csv -v

Options:
  --csv      Path to recruiter CSV (structured source)
  --ats      Path to ATS JSON blob (structured source)
  --resume   Path to resume PDF/DOCX/TXT (unstructured source)
  --notes    Path to recruiter notes .txt (unstructured source)
  --config   Path to runtime output config JSON
  --out      Path to write output JSON (default: print to stdout)
  -v         Verbose / debug logging
"""

import argparse
import json
import sys

from pipeline.pipeline import run


def parse_args():
    parser = argparse.ArgumentParser(
        description="Multi-Source Candidate Data Transformer",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--csv",    metavar="FILE", help="Recruiter CSV export")
    parser.add_argument("--ats",    metavar="FILE", help="ATS JSON blob")
    parser.add_argument("--resume", metavar="FILE", help="Resume PDF/DOCX/TXT")
    parser.add_argument("--notes",  metavar="FILE", help="Recruiter notes .txt")
    parser.add_argument("--config", metavar="FILE", help="Runtime output config JSON")
    parser.add_argument("--out",    metavar="FILE", help="Write output JSON to this file (default: stdout)")
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose debug logging")
    return parser.parse_args()


def main():
    args = parse_args()

    if not any([args.csv, args.ats, args.resume, args.notes]):
        print("ERROR: At least one source file must be provided.", file=sys.stderr)
        print("Use --help for usage.", file=sys.stderr)
        sys.exit(1)

    # Load config if provided
    config = None
    if args.config:
        try:
            with open(args.config, encoding="utf-8") as f:
                config = json.load(f)
        except FileNotFoundError:
            print(f"ERROR: Config file not found: {args.config}", file=sys.stderr)
            sys.exit(1)
        except json.JSONDecodeError as e:
            print(f"ERROR: Invalid JSON in config file: {e}", file=sys.stderr)
            sys.exit(1)

    # Run pipeline
    result = run(
        csv=args.csv,
        ats=args.ats,
        resume=args.resume,
        notes=args.notes,
        config=config,
        output_file=args.out,
        verbose=args.verbose,
    )

    # Print to stdout if no output file specified
    if not args.out:
        print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
