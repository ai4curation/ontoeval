
EXCLUDE_FROM_DIFF = [
    ".claude",
    "CLAUDE.md",
    ".goosehints",
]

def get_redaction_mask_from_diff(diff: str| list[str]) -> dict[str, str]:
    """
    Get a mask from the diff

    Args:
        diff: The diff (which should contain obo syntax diffs)

    Returns:
        A dictionary keywords that should be redacted

    Example:

       >>> diff = ["foo", "+id: GO:0000001", "bar", "+id: GO:0000002", "baz", "+created_by: dragon-ai-agent"]
       >>> mask = get_redaction_mask_from_diff(diff)
       >>> mask
       {'GO:0000001': 'GO:NEW1', 'GO:0000002': 'GO:NEW2', 'dragon-ai-agent': 'REDACTED'}
    """
    if isinstance(diff, str):
        difflines = diff.splitlines()
    else:
        difflines = diff

    import re

    new_id_regex = re.compile(r"^\+id: (\S+)")
    created_by_regex = re.compile(r"^\+created_by: (\S+)")
    contributor_regex = re.compile(r"^\+relationship: dc-contributor: (\S+)")
    dc_date_regex = re.compile(r'^\+property_value: dcterms-date: "(\S+)"')
    obo_date_regex = re.compile(r'^\+creation_date: (\S+)')

    mask = {}
    n = 1
    for line in difflines:
        m = new_id_regex.match(line)
        if m:
            id = m.group(1)
            if ":" in id:
                parts = id.split(":")
                parts[1] = "NEW" + str(n)
                new_id = ":".join(parts)
                mask[id] = new_id
                n += 1
        m = created_by_regex.match(line)
        if m:
            created_by = m.group(1)
            mask[created_by] = "REDACTED"
        m = contributor_regex.match(line)
        if m:
            contributor = m.group(1)
            mask[contributor] = "REDACTED"
        m = dc_date_regex.match(line)
        if m:
            date = m.group(1)
            mask[date] = "REDACTED"
        m = obo_date_regex.match(line)
        if m:
            date = m.group(1)
            mask[date] = "REDACTED"

    return mask

def apply_redaction_mask(diff: str| list[str], mask: dict[str, str]) -> str:
    """
    Apply a redaction mask to a diff

    Args:
        diff: The diff to apply the mask to
        mask: The mask to apply

    Returns:
        The diff with the mask applied

    Example:

        >>> diff = ["foo", "+id: GO:0000001", "bar", "+id: GO:0000002", "baz", "+created_by: dragon-ai-agent", "+relationship: part_of GO:0000001"]
        >>> mask = get_redaction_mask_from_diff(diff)
        >>> print(apply_redaction_mask(diff, mask))
        foo
        +id: GO:NEW1
        bar
        +id: GO:NEW2
        baz
        +created_by: REDACTED
        +relationship: part_of GO:NEW1
    """
    if isinstance(diff, str):
        difflines = diff.splitlines()
    else:
        difflines = diff

    import re

    new_difflines = []
    for line in difflines:
        for keyword, new_value in mask.items():
            # make sure we replace ALL occurrences of the keyword
            line = re.sub(re.escape(keyword), new_value, line)
        new_difflines.append(line)

    return "\n".join(new_difflines)


def trim_diff(diff: str, exclude_files: list[str] | None = None) -> str:
    """
    Trim the diff to exclude files

    Args:
        diff: The diff to trim
        exclude_files: The files to exclude from the diff

    Returns:
        The trimmed diff

    Example:

        >>> lines = ["diff --git a/file1 b/file1", "foo", "diff --git a/file2 b/file2", "bar"]
        >>> diff = chr(10).join(lines)
        >>> print(trim_diff(diff, ["file1"]))
        diff --git a/file2 b/file2
        bar
        >>> assert trim_diff(diff, ["file3"]) == diff

    """
    # split into blocks
    if exclude_files is None:
        exclude_files = EXCLUDE_FROM_DIFF
    blocks = diff.split("diff --git")
    # filter out blocks whose first line contains any of the exclude patterns
    def _exclude_block(block: str) -> bool:
        lines = block.split("\n")
        # print(lines)
        if len(lines) == 0:
            return False
        first_line = lines[0].strip()
        return any(exclude in first_line for exclude in exclude_files)

    blocks = [block for block in blocks if not _exclude_block(block)]
    # join the blocks back together
    return "diff --git".join(blocks)
