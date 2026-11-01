"""Find ordered visual runs with independent offsets across internal cuts.

The full profile's cached hashes are reused unchanged. Row-wise NumPy distance
calculation bounds matrix memory. A weighted interval chain selects disjoint
runs in both timelines, so repeated scenes cannot multiply the coverage.
"""
import heapq
import math
from dataclasses import replace

import numpy as np

from .models import Match
from .video import cancel_check, sparse_segment_fingerprint


def compare_fast_segments(a, b, similarity, coverage, cancel):
    """Conservative ordered runs on a bounded grid. Coverage is an estimate.

    Coarsen both timelines to the same interval before aligning. Never accept
    the ordinary 24-frame quick grid as segment evidence. Runs still need
    changing images, cumulative evidence and disjoint ordered coverage.
    """
    cancel_check(cancel)
    records = []
    for record in (a, b):
        fp = record.fingerprint
        if fp.get('estimated') and fp.get('profile') != 'segments_fast':
            return None
        records.append(replace(record, fingerprint=sparse_segment_fingerprint(fp, record.metadata)))
    step = max(r.fingerprint['step'] for r in records)
    for record in records:
        fp = record.fingerprint
        ratio = step / fp['step']
        if not math.isclose(ratio, round(ratio)):
            return None
        fp['hashes'] = fp['hashes'][::round(ratio)]
        fp['step'] = step
    return _compare_segments(*records, similarity, coverage, cancel, estimated=True)


def compare_segments(a, b, similarity, coverage, cancel):
    return _compare_segments(a, b, similarity, coverage, cancel)


def _compare_segments(a, b, similarity, coverage, cancel, estimated=False):
    cancel_check(cancel)
    duration_a, duration_b = a.metadata['duration'], b.metadata['duration']
    longest = max(duration_a, duration_b)
    if min(duration_a, duration_b) * 100 / longest + 0.01 < coverage:
        return None
    fa, fb = a.fingerprint, b.fingerprint
    # Sparse samples do not establish continuous matching segments.
    if not estimated and (fa.get('estimated') or fb.get('estimated')):
        return None
    ha, hb = fa['hashes'], fb['hashes']
    sa, sb = fa['step'], fb['step']
    if not math.isclose(sa, sb):
        return None
    step = sa
    minimum_run = max(3, math.ceil(min(2.0, min(duration_a, duration_b) / 2) / step))
    if min(len(ha), len(hb)) < minimum_run:
        return None
    values_b = np.array([h if h is not None else 0 for h in hb], dtype=np.uint64)
    valid_b = np.array([h is not None for h in hb])
    lengths = np.zeros(len(hb), dtype=np.int32)
    totals = np.zeros(len(hb), dtype=float)
    limit = (1 - similarity / 100) * 63 + 1e-8
    distances_matrix = None
    if estimated:
        # This profile has at most 160 captures per timeline. A small vectorized
        # screen rejects pairs unable to reach coverage before the run search.
        values_a = np.array([h if h is not None else 0 for h in ha], dtype=np.uint64)
        valid_a = np.array([h is not None for h in ha])
        distances_matrix = np.bitwise_count(values_a[:, None] ^ values_b[None, :])
        possible = (distances_matrix <= limit) & valid_a[:, None] & valid_b[None, :]
        upper_seconds = min(possible.any(axis=1).sum() * step, possible.any(axis=0).sum() * step,
                            duration_a, duration_b)
        if upper_seconds * 100 / longest + 1e-8 < coverage:
            return None
    evidence_floor = math.log(max(1, len(ha) * len(hb)) * 1000)
    runs = []

    def finish(row, ends):
        for end in ends:
            length = int(lengths[end])
            score = float(totals[end]) / length
            # Flexible alignment creates many opportunities for random matches
            # at loose thresholds. Require stronger cumulative evidence from
            # short/weak runs. This is a collision heuristic, not a confidence
            # probability: perceptual hash bits need not be independent.
            evidence = 2 * 63 * length * max(0, (score - 50) / 100) ** 2
            if evidence < evidence_floor:
                continue
            start_a, start_b = row - length, int(end) + 1 - length
            # Uniform frames have no hash. Repeated stills and near-identical
            # hashes also cannot establish a sequence of distinct images.
            samples_a = ha[start_a:row]
            samples_b = hb[start_b:int(end) + 1]
            if not _changing_sequence(samples_a) or not _changing_sequence(samples_b):
                continue
            seconds = min(row * step, duration_a) - start_a * step
            seconds = min(seconds, min((int(end) + 1) * step, duration_b) - start_b * step)
            if seconds > 0:
                runs.append((start_a, row, start_b, int(end) + 1, seconds, score))

    for i, h in enumerate(ha):
        cancel_check(cancel)
        distances = distances_matrix[i] if distances_matrix is not None else np.bitwise_count(values_b ^ np.uint64(h if h is not None else 0))
        hits = (distances <= limit) & valid_b & (h is not None)
        # Previous cell (i-1,j) continues only at current cell (i,j+1).
        continues = np.append(hits[1:], False)
        finish(i, np.flatnonzero((lengths >= minimum_run) & ~continues))
        scores = (1 - distances.astype(float) / 63) * 100
        lengths = np.where(hits, np.r_[0, lengths[:-1]] + 1, 0)
        totals = np.where(hits, np.r_[0.0, totals[:-1]] + scores, 0.0)
    finish(len(ha), np.flatnonzero(lengths >= minimum_run))
    if not runs:
        return None
    chain = _ordered_chain(runs, len(hb), cancel)
    seconds = sum(run[4] for run in chain)
    covered = min(100.0, seconds / longest * 100)
    if covered + 1e-8 < coverage:
        return None
    spans = [[r[0] * step, min(r[1] * step, duration_a), r[2] * step, min(r[3] * step, duration_b)] for r in chain]
    score = sum(r[5] * r[4] for r in chain) / seconds
    return Match(a.key, b.key, 'similar', score, covered, spans, estimated)


def _changing_sequence(hashes):
    if len(set(hashes)) < 3:
        return False
    first = hashes[0]
    return any((first ^ h).bit_count() >= 4 for h in hashes[1:])


def _ordered_chain(runs, width, cancel):
    """Maximum covered duration, with no overlap or reversal on either axis."""
    runs.sort(key=lambda r: (r[0], r[2], r[1], r[3]))
    tree = [(-0.0, -1)] * (width + 2)
    pending = []
    weights, parents = [], []
    best = (0.0, -1)
    for index, run in enumerate(runs):
        cancel_check(cancel)
        while pending and pending[0][0] <= run[0]:
            _, previous = heapq.heappop(pending)
            pos = runs[previous][3] + 1
            value = (weights[previous], previous)
            while pos < len(tree):
                tree[pos] = max(tree[pos], value)
                pos += pos & -pos
        pos = run[2] + 1
        prior = (0.0, -1)
        while pos:
            prior = max(prior, tree[pos])
            pos -= pos & -pos
        weights.append(prior[0] + run[4])
        parents.append(prior[1])
        best = max(best, (weights[-1], index))
        heapq.heappush(pending, (run[1], index))
    chain = []
    index = best[1]
    while index >= 0:
        chain.append(runs[index])
        index = parents[index]
    return list(reversed(chain))
