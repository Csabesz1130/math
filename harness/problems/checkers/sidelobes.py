"""Trusted checker for binary-code problems.

check(candidate) accepts a list of +1/-1 entries (or an object with a
"sequence" key) and returns {"ok", "message", "score"}; the score is higher
for lower peak sidelobe level, with integrated sidelobe level as tie-break.
"""

LENGTH = None  # set by the problem file's checker preamble
MAX_PSL = None


def check(candidate):
    seq = candidate.get("sequence") if isinstance(candidate, dict) else candidate
    if not isinstance(seq, list) or any(x not in (1, -1) for x in seq):
        return {"ok": False, "message": "expected a list of +1/-1 entries"}
    if LENGTH is not None and len(seq) != LENGTH:
        return {"ok": False, "message": f"length {len(seq)}, expected {LENGTH}"}
    n = len(seq)
    corr = [sum(seq[j] * seq[j + k] for j in range(n - k)) for k in range(1, n)]
    psl = max((abs(c) for c in corr), default=0)
    isl = sum(c * c for c in corr)
    ok = MAX_PSL is None or psl <= MAX_PSL
    return {"ok": ok, "message": f"PSL {psl}, ISL {isl}", "score": -(psl + isl / 1e6)}
