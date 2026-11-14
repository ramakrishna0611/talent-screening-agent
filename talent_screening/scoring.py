"""Deterministic, explainable scoring. No LLM here: the same resume text and job always give the same score.

Criteria (weights from the job, default 40/20/15/25):
- must_have:    required skill groups (a group like ["power bi", "tableau"] is satisfied by either).
                Full credit when the skill is shown in work or projects, half credit when it is only listed.
- experience:   RELEVANT experience (months in roles whose description uses the job's skills) vs the minimum
- nice_to_have: optional skills, same full/half credit rule
- applied:      share of the job's skills that appear inside work highlights or project descriptions
Listing skills without showing them in work earns little, so keyword stuffing does not rank well.

The candidate's name, email and phone are never read here.
"""
from dataclasses import asdict, dataclass, field

from talent_screening.config import DEFAULT_WEIGHTS
from talent_screening.extract import Profile, experience_years
from talent_screening.skills import display, find_in_text


@dataclass
class Criterion:
    name: str
    points: float
    max_points: float
    detail: str
    evidence: list[dict] = field(default_factory=list)     # [{"skill":..., "quote":...}]


def applied_text(profile: Profile) -> str:
    """Text describing work actually done: role highlights and project descriptions (not the skills list)."""
    parts = []
    for r in profile.roles:
        parts.append(r.title)
        parts.extend(r.highlights)
    for p in profile.projects:
        parts.append(p.name + ". " + p.description)
    return "\n".join(parts)


def score(profile: Profile, resume_text: str, job, today=None) -> dict:
    w = {**DEFAULT_WEIGHTS, **(job.weights or {})}
    criteria: list[Criterion] = []

    used_text = applied_text(profile)

    def credit(options: list[str]) -> tuple[float, dict | None]:
        """1.0 if shown in work/projects, 0.5 if only mentioned elsewhere in the resume, else 0."""
        for s in options:
            if q := find_in_text(s, used_text):
                return 1.0, {"skill": display(s), "quote": q, "credit": "used in work"}
        for s in options:
            if q := find_in_text(s, resume_text):
                return 0.5, {"skill": display(s), "quote": q, "credit": "listed only (half)"}
        return 0.0, None

    # 1. Must-have skill groups, verified against the resume text
    groups = job.must_have or []
    got, missing, ev = 0.0, [], []
    for group in groups:
        c, e = credit(group)
        got += c
        if e:
            ev.append(e)
        else:
            missing.append(" / ".join(display(s) for s in group))
    pts = w["must_have"] * (got / len(groups) if groups else 1)
    half = sum(1 for e in ev if e["credit"].startswith("listed"))
    criteria.append(Criterion("Must-have skills", pts, w["must_have"],
                              f"{len(groups) - len(missing)} of {len(groups)} present"
                              + (f" ({half} only listed, half credit)" if half else "")
                              + (f"; missing: {', '.join(missing)}" if missing else ""), ev))

    # 2. Relevant experience: only roles whose own description uses at least one of the job's skills
    all_skills = [s for g in groups for s in g] + list(job.nice_to_have or [])
    relevant = [r for r in profile.roles
                if any(find_in_text(s, " ".join([r.title, *r.highlights])) for s in all_skills)]
    years = experience_years(relevant, today)
    total_years = experience_years(profile.roles, today)
    need = job.min_years or 0
    ratio = 1.0 if need <= 0 else min(1.0, years / need)
    criteria.append(Criterion("Relevant experience", w["experience"] * ratio, w["experience"],
                              f"{years} years in relevant roles (job asks for {need:g}+; total experience {total_years})",
                              [{"skill": r.title, "quote": f"{r.company}, {r.start} to {r.end}"} for r in relevant]))

    # 3. Nice-to-have skills (same full/half credit rule)
    nice = job.nice_to_have or []
    results = [credit([s]) for s in nice]
    pts = w["nice_to_have"] * (sum(c for c, _ in results) / len(nice) if nice else 1)
    criteria.append(Criterion("Nice-to-have skills", pts, w["nice_to_have"],
                              f"{sum(1 for c, _ in results if c)} of {len(nice)} present",
                              [e for _, e in results if e]))

    # 4. Skills applied in work or projects (not only listed)
    job_skills = [g[0] if len(g) == 1 else g for g in groups] + list(nice)
    applied, listed_only = [], []
    for item in job_skills:
        options = item if isinstance(item, list) else [item]
        hit = next(((s, q) for s in options if (q := find_in_text(s, used_text))), None)
        label = " / ".join(display(s) for s in options)
        if hit:
            applied.append({"skill": label, "quote": hit[1]})
        elif any(find_in_text(s, resume_text) for s in options):
            listed_only.append(label)
    pts = w["applied"] * (len(applied) / len(job_skills) if job_skills else 1)
    criteria.append(Criterion("Applied in work or projects", pts, w["applied"],
                              f"{len(applied)} of {len(job_skills)} job skills shown in actual work"
                              + (f"; listed but not shown in work: {', '.join(listed_only)}" if listed_only else ""),
                              applied))

    total = round(sum(c.points for c in criteria))
    return {
        "score": total,
        "experience_years": years,
        "total_experience_years": total_years,
        "missing_must_have": missing,
        "criteria": [{**asdict(c), "points": round(c.points, 1)} for c in criteria],
    }
