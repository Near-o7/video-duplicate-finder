"""Explicit bulk selection: propose redundant copies while retaining references."""


def redundant_keys(result, visible, allow_primary=False):
    visible = set(visible)
    eligible = {k for k in visible if result.files[k].active and not result.files[k].error and
                (not result.options.secondary or result.files[k].root == "secondary" or allow_primary)}
    selected, keep = set(), set()
    for group in result.exact_groups:
        group = [k for k in group if result.files[k].active and not result.files[k].error]
        if len(group) < 2:
            continue
        group.sort(key=lambda k: (result.files[k].root != "primary", k))
        reference = next((k for k in group if k not in eligible), group[0])
        keep.add(reference)
        selected.update(k for k in group if k in eligible and k != reference)
    # A segment match may share only a small portion of the longer video.
    # It does not establish a redundant copy for automatic bulk proposals.
    if result.options.video_profile in ('segments', 'segments_fast'):
        return selected
    for match in result.similar_matches:
        a, b = match.a, match.b
        if not result.files[a].active or not result.files[b].active or a in selected or b in selected:
            continue
        if a in keep and b in keep:
            continue
        if b in keep or (a not in keep and (result.files[b].root == "primary" or a in eligible and b not in eligible)):
            a, b = b, a
        if b in eligible and b not in keep:
            keep.add(a)
            selected.add(b)
    return selected
