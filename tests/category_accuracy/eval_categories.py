#!/usr/bin/env python3
"""Score the main category of a hand-labelled sample against votes.json.

    python tests/category_accuracy/eval_categories.py 4

Each sampleN_ids.json is a random sample of vote ids; sampleN_labels.py holds
the labeller's primary category and acceptable alternates for each vote,
written from the agenda title alone (before looking at the scheme's answer).
"exact" = matches the primary label; "acceptable" = primary or an alternate.
"""
import collections
import importlib.util
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))


def main(n):
    spec = importlib.util.spec_from_file_location("labels", os.path.join(HERE, f"sample{n}_labels.py"))
    labels = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(labels)
    ids = json.load(open(os.path.join(HERE, f"sample{n}_ids.json")))
    votes = {v["id"]: v for v in json.load(open(os.path.join(ROOT, "votes.json")))["votes"]}
    exact = ok = 0
    misses = []
    for i, vid in enumerate(ids, 1):
        primary, alts = labels.L[i]
        got = votes[vid]["category"]
        exact += got == primary
        good = got == primary or got in alts
        ok += good
        if not good:
            misses.append((i, got, primary, sorted(alts), votes[vid]["title"][:70]))
    total = len(ids)
    print(f"sample {n}: exact {exact}/{total} = {100*exact/total:.0f}%   acceptable {ok}/{total} = {100*ok/total:.0f}%")
    for i, got, primary, alts, title in misses:
        print(f"  {i:3d}. got {got:24s} expected {primary} {alts or ''} | {title}")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 4)
