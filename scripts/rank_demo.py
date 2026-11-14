"""Extract every sample resume once (LLM), then score it against every job (code) and print the rankings.

Run:  python scripts/rank_demo.py
"""
import json
import sys
import time
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from talent_screening.config import DATA
from talent_screening.extract import extract_profile
from talent_screening.models import Job, make_session_factory
from talent_screening.parsing import suspicious_phrases
from talent_screening.scoring import score

TODAY = date(2026, 11, 14)
CACHE = DATA / "profiles_cache.json"


def main() -> None:
    db = make_session_factory()()
    jobs = db.query(Job).order_by(Job.code).all()
    cache = json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {}
    profiles = {}
    for f in sorted((DATA / "resumes").glob("*.txt")):
        text = f.read_text(encoding="utf-8")
        if f.stem not in cache:
            t = time.time()
            cache[f.stem] = extract_profile(text).model_dump()
            print(f"extracted {f.stem:18s} {time.time() - t:4.1f}s")
        from talent_screening.extract import Profile
        profiles[f.stem] = (Profile.model_validate(cache[f.stem]), text)
    CACHE.write_text(json.dumps(cache, indent=1), encoding="utf-8")

    for job in jobs:
        rows = sorted(((score(p, text, job, TODAY), name, bool(suspicious_phrases(text)))
                       for name, (p, text) in profiles.items()), key=lambda r: -r[0]["score"])
        print(f"\n{job.code}  {job.title}")
        for r, name, flagged in rows[:6]:
            parts = " ".join(f"{c['points']:>4}/{c['max_points']:<2}" for c in r["criteria"])
            print(f"  {r['score']:>3}  {name:18s} {parts}  exp={r['experience_years']}"
                  + ("  [INJECTION FLAG]" if flagged else ""))


if __name__ == "__main__":
    main()
