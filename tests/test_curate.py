from collections import Counter

from arena.curate import BaselineOutcome, assemble_sets, sample_candidates


def rows():
    out = []
    repos = ["django/django"] * 231 + ["sympy/sympy"] * 75 + ["sphinx-doc/sphinx"] * 44 + ["matplotlib/matplotlib"] * 34 + ["scikit-learn/scikit-learn"] * 32 + ["astropy/astropy"] * 22 + ["pydata/xarray"] * 22 + ["pytest-dev/pytest"] * 19 + ["pylint-dev/pylint"] * 10 + ["psf/requests"] * 8 + ["mwaskom/seaborn"] * 2 + ["pallets/flask"] * 1
    for i, repo in enumerate(repos):
        diff = ["<15 min fix", "15 min - 1 hour", "1-4 hours", ">4 hours"][i % 4 if i % 10 < 2 else i % 2]
        out.append({"instance_id": f"{repo.replace('/', '__')}-{i}", "repo": repo, "difficulty": diff})
    return out


def test_sample_respects_cap_and_difficulty():
    picked = sample_candidates(rows(), n=200)
    assert len(picked) == 200
    assert all(p["difficulty"] in ("<15 min fix", "15 min - 1 hour") for p in picked)
    assert max(Counter(p["repo"] for p in picked).values()) <= 40


def test_assemble_disjoint_and_dev_subset():
    outcomes = []
    for i, r in enumerate(sample_candidates(rows(), n=200)):
        outcomes.append(BaselineOutcome(r["instance_id"], r["repo"], solved=[0, 1, 2, 3][i % 4], cost_usd=0.1))
    sets = assemble_sets(outcomes)
    assert len(sets["public"]) == 50 and len(sets["private"]) == 100 and len(sets["dev"]) == 5
    assert not set(sets["public"]) & set(sets["private"])
    assert set(sets["dev"]) <= set(sets["public"])
