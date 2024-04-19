import itertools


def full_groupby(iterable, key):
    return itertools.groupby(sorted(iterable, key=key), key=key)
