"""Generate AI summaries for the demo applications once and store them in data/demo_summaries.json,
so the hosted demo shows complete scorecards without spending LLM quota.

Run:  python scripts/build_demo_summaries.py      (resumable: skips summaries already saved)
"""
import json
import sys
import time
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from openai import RateLimitError

from talent_screening.config import DATA
from talent_screening.extract import Profile
from talent_screening.models import Job, make_session_factory
from talent_screening.scoring import score
from talent_screening.seed import DEMO_APPLICATIONS, seed
from talent_screening.summary import summarize

OUT = DATA / "demo_summaries.json"


def main() -> None:
    db = make_session_factory("sqlite:///:memory:")()
    seed(db)
    profiles = json.loads((DATA / "demo_profiles.json").read_text(encoding="utf-8"))
    done = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
    for code, names in DEMO_APPLICATIONS.items():
        job = db.query(Job).filter_by(code=code).one()
        for name in names:
            key = f"{code}:{name}"
            if key in done:
                continue
            profile = Profile.model_validate(profiles[name])
            text = (DATA / "resumes" / f"{name}.txt").read_text(encoding="utf-8")
            breakdown = score(profile, text, job, date(2026, 11, 14))
            for attempt in range(20):
                try:
                    done[key] = summarize(job, profile, breakdown)
                    break
                except RateLimitError:
                    print(f"  rate limited on {key}, waiting 60 s", flush=True)
                    time.sleep(60)
            OUT.write_text(json.dumps(done, indent=1, ensure_ascii=False), encoding="utf-8")
            print(f"saved {key}", flush=True)
    print(f"{len(done)} summaries in {OUT}")


if __name__ == "__main__":
    main()
