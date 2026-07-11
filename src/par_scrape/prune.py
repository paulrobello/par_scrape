"""Boilerplate pruning for converted page markdown (ENH-003).

Reduces LLM input tokens by removing navigation bars, footers, link farms, and
other boilerplate that never carries extractable fields. Conservative by design:
headings, tables, code blocks, and any line containing a digit (prices, specs)
are always preserved. Opt-in via the CLI ``--prune`` flag, so the default
behavior is unchanged.

Only the markdown handed to the LLM is pruned; the raw saved file and the
ENH-002 content hash both use the unpruned markdown, so on-disk artifacts and
incremental-rescrape match keys are unaffected.
"""

import re

# A fenced code-block delimiter: an indented line of three or more backticks or
# tildes. While inside a fence, every line is emitted verbatim.
_FENCE_RE = re.compile(r"^\s{0,3}(```|~~~)")

# A Markdown list marker: ``- ``, ``* ``, ``+ ``, or ``1. ``.
_LIST_MARKER_RE = re.compile(r"^\s{0,3}(?:[-*+]\s+|\d+\.\s+)")

# A Markdown link ``[text](url)``; group 1 is the text.
_LINK_RE = re.compile(r"\[([^\]]*)\]\([^)]*\)")

# A body that is exactly one link (``[text](url)`` and nothing else).
_LINK_ONLY_RE = re.compile(r"^\[([^\]]*)\]\([^)]*\)$")

# A whole line that is only a bare URL or only an image reference.
_BARE_URL_RE = re.compile(r"^(?:https?://|//|www\.)\S+$", re.IGNORECASE)
_IMAGE_ONLY_RE = re.compile(r"^!\[([^\]]*)\]\([^)]*\)$")

_HEADING_RE = re.compile(r"^#{1,6}\s")
_TABLE_RE = re.compile(r"^\s*\|")
_DIGIT_RE = re.compile(r"\d")
# Three or more consecutive newlines (two or more blank lines) to be collapsed.
_BLANK_RUN_RE = re.compile(r"\n{3,}")

# Minimum run length for rule 2: a block of this many consecutive link-only list
# items is treated as a nav menu / footer and dropped.
_LINK_ITEM_RUN_MIN = 4


def _body(line: str) -> str:
    """Return ``line`` with any leading list marker removed.

    The marker is stripped before the digit/price guard runs so that an ordered
    list's own index (``1.``, ``2.`` ...) does not shield nav links from rule 2.
    """
    return _LIST_MARKER_RE.sub("", line, count=1)


def _protected(line: str, body: str) -> bool:
    """True when no pruning rule may remove ``line``.

    Headings, tables, fence delimiters, and any line whose body contains a digit
    (prices, specs, model numbers) are preserved unconditionally.
    """
    if _FENCE_RE.match(line):
        return True
    if _HEADING_RE.match(line.lstrip()):
        return True
    if _TABLE_RE.match(line):
        return True
    return _DIGIT_RE.search(body) is not None


def prune_markdown(markdown: str) -> str:
    """Remove boilerplate unlikely to contain extractable data.

    Rules, applied with a strong keep-bias:

    - Empty-text link list items (``- [](url)``) are dropped.
    - A run of four or more consecutive list items that are each a single link
      (a nav menu or footer link farm) is dropped.
    - Lines whose body is only a bare URL or only an image reference are dropped.
    - Headings, tables, code-block content, and any line containing a digit are
      never removed.
    - Trailing whitespace is stripped per line and runs of blank lines collapse
      to a single blank line.

    Args:
        markdown: The full converted page markdown.

    Returns:
        The pruned markdown. Input with no droppable boilerplate is returned
        byte-identical (apart from trailing-whitespace and blank-line tidying).
    """
    if not markdown:
        return ""

    lines = markdown.split("\n")

    # Pass 1: per-line classification, respecting code-fence state. ``drop``
    # holds the single-line verdict (rules 1 and 3); rule 2 needs a window of
    # neighbours and is resolved in pass 2.
    in_fence = False
    protected_flags: list[bool] = []
    link_only: list[bool] = []
    drop: list[bool] = []

    for line in lines:
        is_fence = bool(_FENCE_RE.match(line))
        if is_fence:
            in_fence = not in_fence

        body = _body(line)
        # Everything inside a code block is emitted verbatim.
        if in_fence and not is_fence:
            protected_flags.append(True)
            link_only.append(False)
            drop.append(False)
            continue

        is_list = bool(_LIST_MARKER_RE.match(line))
        protected_flags.append(_protected(line, body))
        link_only.append(is_list and _LINK_ONLY_RE.match(body.strip()) is not None)

        # Rule 1: a list item whose text vanishes once link URLs are stripped.
        rule1 = is_list and _LINK_RE.sub(r"\1", body).strip() == ""
        # Rule 3: a body that is only a bare URL or only an image.
        stripped_body = body.strip()
        rule3 = bool(_BARE_URL_RE.match(stripped_body) or _IMAGE_ONLY_RE.match(stripped_body))
        drop.append(rule1 or rule3)

    # Pass 2: rule 2 — collapse runs of consecutive link-only, unprotected list
    # items of length >= _LINK_ITEM_RUN_MIN.
    run_start: int | None = None
    count = len(lines)
    for i in range(count + 1):
        active = i < count and link_only[i] and not protected_flags[i]
        if active:
            if run_start is None:
                run_start = i
        elif run_start is not None:
            if i - run_start >= _LINK_ITEM_RUN_MIN:
                for j in range(run_start, i):
                    drop[j] = True
            run_start = None

    # Emit, skipping dropped lines (protected lines always survive).
    kept = [line.rstrip() for i, line in enumerate(lines) if not (drop[i] and not protected_flags[i])]
    result = "\n".join(kept)
    result = _BLANK_RUN_RE.sub("\n\n", result)
    return result
