import functools
import textwrap


@functools.lru_cache(maxsize=128)
def dedent_strip(text):
    return textwrap.dedent(text).strip()
