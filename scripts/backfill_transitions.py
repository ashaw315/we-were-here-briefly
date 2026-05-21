"""
Backfill Kling O1 transitions for every existing run, then assemble the
final loop video.

For each chronological pair (run_i → run_i+1) this generates a transition
and stores its URL on run_i. A final loop-closing transition joins the
last run back to the first and is stored on the last run. After all
transitions exist, assemble_final_video() rebuilds and republishes the
HLS stream.

The backfill is RESUMABLE: a run whose transition_url is already set is
skipped, so if the script is interrupted at transition 45/54 it picks up
at 45 rather than regenerating from 1.

Errors are handled per-transition — one failed Kling generation is logged
and the backfill continues to the next pair.

Usage:
  python scripts/backfill_transitions.py --dry-run   # list, no API/DB
  python scripts/backfill_transitions.py --limit 3   # first 3 only (test)
  python scripts/backfill_transitions.py             # full backfill
"""

import argparse
import os
import sys
import time

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from db.database import get_all_runs_ordered, update_transition_url
from generator.transition_gen import generate_transition
from assembler.assemble import assemble_final_video


def build_plan(runs):
    """
    Build the ordered list of transitions to generate.

    Each entry is a dict describing one transition:
      from_run, to_run, is_loop (True for the last → first closer).

    The loop-closing transition is always last.
    """
    plan = []
    for i in range(len(runs) - 1):
        plan.append({
            "from_run": runs[i],
            "to_run": runs[i + 1],
            "is_loop": False,
        })
    if len(runs) >= 2:
        plan.append({
            "from_run": runs[-1],
            "to_run": runs[0],
            "is_loop": True,
        })
    return plan


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run", action="store_true",
        help="List the transitions that would be generated; no API/DB writes.",
    )
    parser.add_argument(
        "--limit", type=int, default=None,
        help="Generate only the first N consecutive transitions (testing). "
             "Skips the loop-closing transition.",
    )
    args = parser.parse_args()

    runs = get_all_runs_ordered()
    if not runs or len(runs) < 2:
        print("Need at least 2 runs to build transitions.")
        sys.exit(1)

    plan = build_plan(runs)

    # --limit keeps only the first N consecutive transitions (drops the
    # loop-closer), so a small live test doesn't try to close the loop.
    if args.limit is not None:
        consecutive = [p for p in plan if not p["is_loop"]]
        plan = consecutive[: args.limit]

    total = len(plan)
    print(f"Found {len(runs)} runs — generating {total} transitions "
          f"(including loop-closing transition)"
          if args.limit is None else
          f"Found {len(runs)} runs — generating {total} transitions "
          f"(--limit {args.limit}, loop-closer skipped)")

    if args.dry_run:
        print("\n[DRY RUN] transitions that would be generated:")
        for idx, p in enumerate(plan, start=1):
            a, b = p["from_run"], p["to_run"]
            tag = " (loop-closing)" if p["is_loop"] else ""
            status = "SKIP (exists)" if a.get("transition_url") else "generate"
            print(f"  {idx}/{total}: {a['seed']} → {b['seed']}{tag} "
                  f"[{status}]")
        print("\n[DRY RUN] no API calls or DB writes made. Assembly skipped.")
        return

    generated = 0
    skipped = 0
    failed = 0

    for idx, p in enumerate(plan, start=1):
        a, b = p["from_run"], p["to_run"]
        tag = " (loop-closing)" if p["is_loop"] else ""

        # Resume support: skip pairs whose transition already exists.
        if a.get("transition_url"):
            print(f"Transition {idx}/{total}: {a['seed']} → {b['seed']}{tag} "
                  f"— skipped (already exists)")
            skipped += 1
            continue

        print(f"Transition {idx}/{total}: {a['seed']} → {b['seed']}{tag}")
        try:
            url = generate_transition(
                a["video_url"], b["video_url"],
                a["id"], b["id"],
                seed_a=a.get("seed"), seed_b=b.get("seed"),
            )
            update_transition_url(a["id"], url)
            # Keep the in-memory run in sync so later skip checks are correct.
            a["transition_url"] = url
            generated += 1
            if p["is_loop"]:
                print("Loop-closing transition complete")
            else:
                print(f"Transition {idx}/{total} complete")
        except Exception as e:
            failed += 1
            print(f"  ✗ Transition {idx}/{total} FAILED: "
                  f"{type(e).__name__}: {e} — continuing")

        # Rate-limit courtesy between generations.
        if idx < total:
            time.sleep(2)

    # Rebuild + republish the final video from whatever transitions exist.
    print("\nRebuilding final video...")
    playlist_url = assemble_final_video()

    print("\n" + "=" * 50)
    print("BACKFILL SUMMARY")
    print("=" * 50)
    print(f"{generated} transitions generated")
    print(f"{skipped} transitions skipped (already existed)")
    if failed:
        print(f"{failed} transitions FAILED")
    if playlist_url:
        print(f"Final video rebuilt and uploaded to R2: {playlist_url}")
    else:
        print("Final video assembly did not complete (see logs above)")


if __name__ == "__main__":
    main()
