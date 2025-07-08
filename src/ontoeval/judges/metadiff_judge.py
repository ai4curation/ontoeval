from difflib import unified_diff
from pathlib import Path
import re
from pydantic import BaseModel

from ontoeval.models import Change, Comparison, PRBenchmark

IGNORE_KEYS = ["created_by", "creation_date", "property_value: dcterms-date", "relationship: dc-contributor"]

class MetadiffComparison(Comparison):
    similarity: float
    identical: bool | None = None
    metadiff: list[str] | None = None
    metadiff_color_text: str | None = None
    metadiff_color_html: str | None = None
    changes_in_common: list[Change] | None = None
    changes_in_diff1: list[Change] | None = None
    changes_in_diff2: list[Change] | None = None
    num_changes_in_common: int | None = None
    num_changes_in_diff1: int | None = None
    num_changes_in_diff2: int | None = None
    f1_score: float | None = None
    precision: float | None = None
    recall: float | None = None

def lines_to_changes(lines: list[str], mask_ids: bool = True) -> list[Change]:
    """
    Convert a list of lines to a list of changes.

    By default this masks CURIE IDs. The rationale is that we don't expect ID
    identity for new term requests.

    For referencing a term, obof includes the label after the ! comment,
    so we will still be able to tell if the intent differs
    
    Args:
        lines: The list of lines to convert to changes.
        mask_ids: If true, mask any CURIE IDs in the lines.

    Returns:
        A list of changes.

    Example:
        >>> lines_to_changes(["+a", "-b", "+c"])
        [(1, 'a'), (-1, 'b'), (1, 'c')]

    Masking IDs:

        >>> lines_to_changes(["+GO:0000001", "-GO:0000002", "+GO:0000003 ! foo"], mask_ids=True)
        [(1, 'GO:NNNNNNN'), (-1, 'GO:NNNNNNN'), (1, 'GO:NNNNNNN ! foo')]

    """
    changes: list[Change] = []
    import re
    for line in lines:
        line = line.strip()
        if line.startswith("---"):
            continue
        if line.startswith("+++"):
            continue
        if mask_ids:
            # preserve the prefix but change the numeric part;
            # e.g. foo GO:0000001 bar -> foo GO:NNNNNNN bar
            line = re.sub(r"([a-zA-Z0-9]+):(\d+)(.*)", r"\1:NNNNNNN\3", line)
        if not line:
            continue
        if not line[1:].strip():
            continue
        for key in IGNORE_KEYS:
            if key in line:
                continue
        if line.startswith("+"):
            changes.append((+1, line[1:]))
        elif line.startswith("-"):
            changes.append((-1, line[1:]))
    return changes

def compare_diffs(diff1: str | list[str], diff2: str | list[str], silent=False, pr_benchmark: PRBenchmark = None, **kwargs) -> MetadiffComparison:
    """
    Compare two diffs and return a comparison object.

    Args:
        diff1: The first diff to compare.
        diff2: The second diff to compare.
        **kwargs: Additional keyword arguments to pass to lines_to_changes.

    Returns:
        A Comparison object.

    Example:

        >>> c = compare_diffs(["+a", "-b", "+c"], ["+a", "-b", "+d"], silent=True)
        >>> c.similarity
        0.5
        >>> c.identical
        False

    """
    if not diff1:
        diff1 = ""
    if not diff2:
        diff2 = ""
    diff1 = diff1.splitlines() if isinstance(diff1, str) else diff1
    diff2 = diff2.splitlines() if isinstance(diff2, str) else diff2
    metadiff_color_text = visual_diff("\n".join(diff1), "\n".join(diff2), silent=silent)
    metadiff_color_html = ansi_to_html(metadiff_color_text)
    changes1 = set(lines_to_changes(diff1, **kwargs))
    changes2 = set(lines_to_changes(diff2, **kwargs))
    # calculate the similarity as the ratio of changes1 to changes2
    tot_changes = len(changes1 | changes2)
    similarity = len(changes1 & changes2) / tot_changes if tot_changes > 0 else 0.0
    metadiff = list(unified_diff(diff1, diff2))
    changes_in_common=list(changes1 & changes2)
    changes_in_diff1=list(changes1 - changes2)
    changes_in_diff2=list(changes2 - changes1)
    return MetadiffComparison(
        identical=unified_diff(diff1, diff2) == "",
        similarity=similarity,
        metadiff=metadiff,
        metadiff_color_text=metadiff_color_text,
        metadiff_color_html=metadiff_color_html,
        changes_in_common=changes_in_common,
        changes_in_diff1=changes_in_diff1,
        changes_in_diff2=changes_in_diff2,
        num_changes_in_common=len(changes_in_common), # aka true positives
        num_changes_in_diff1=len(changes_in_diff1), # aka false negatives
        num_changes_in_diff2=len(changes_in_diff2), # aka false positives
        precision=len(changes_in_common) / len(changes1) if len(changes1) > 0 else 0.0,
        recall=len(changes_in_common) / len(changes2) if len(changes2) > 0 else 0.0,
        f1_score=2 * len(changes_in_common) / (len(changes1) + len(changes2)) if len(changes1) > 0 and len(changes2) > 0 else 0.0,
    )

def visual_diff(diff1: str, diff2: str, silent=False, **kwargs) -> str:
    """
    Use icdiff to visualize the diff.

    Args:
        diff1: The first diff to visualize.
        diff2: The second diff to visualize.
        silent: If true, do not print the diff to the console.
        **kwargs: Additional keyword arguments to pass to icdiff.

    Returns:
        A string of the diff.

    Side-effect:
        Prints the diff to the console.

    Under the hood:

        icdiff file1 file2
    """
    import tempfile
    import subprocess
    # TODO: use a context manager AND do everything in context:
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpf1 = Path(tmpdir) / "diff1.diff"
        tmpf1.write_text(diff1)
        tmpf2 = Path(tmpdir) / "diff2.diff"
        tmpf2.write_text(diff2)
        cmd = ["icdiff", str(tmpf1), str(tmpf2), "-E", "@@"]
        # print(" ".join(cmd))
        #subprocess.run(cmd, check=False)
        # run again, capture the output
        output = subprocess.run(cmd, check=False, capture_output=True, text=True)
        if not silent:
            print(output.stdout)
        return output.stdout
    
    import re

def ansi_to_html(text):
    """Convert ANSI escape sequences to HTML spans with appropriate colors."""
    
    # ANSI color mappings (icdiff commonly uses these)
    color_map = {
        '30': 'black',
        '31': 'red',
        '32': 'green', 
        '33': 'yellow',
        '34': 'blue',
        '35': 'magenta',
        '36': 'cyan',
        '37': 'white',
        '90': '#808080',  # bright black (gray)
        '91': '#ff6b6b',  # bright red
        '92': '#51cf66',  # bright green
        '93': '#ffd43b',  # bright yellow
        '94': '#74c0fc',  # bright blue
        '95': '#f06292',  # bright magenta
        '96': '#22d3ee',  # bright cyan
        '97': '#f8f9fa'   # bright white
    }
    
    # Background color mappings
    bg_color_map = {
        '40': 'black',
        '41': 'red',
        '42': 'green',
        '43': 'yellow',
        '44': 'blue',
        '45': 'magenta',
        '46': 'cyan',
        '47': 'white',
        '100': '#808080',  # bright black bg
        '101': '#ff6b6b',  # bright red bg
        '102': '#51cf66',  # bright green bg
        '103': '#ffd43b',  # bright yellow bg
        '104': '#74c0fc',  # bright blue bg
        '105': '#f06292',  # bright magenta bg
        '106': '#22d3ee',  # bright cyan bg
        '107': '#f8f9fa'   # bright white bg
    }
    
    # Replace ANSI escape sequences with HTML
    def replace_ansi(match):
        codes = match.group(1).split(';')
        styles = []
        
        for code in codes:
            if code == '0' or code == '':  # Reset
                return '</span>'
            elif code == '1':  # Bold
                styles.append('font-weight: bold')
            elif code == '4':  # Underline
                styles.append('text-decoration: underline')
            elif code in color_map:  # Foreground colors
                styles.append(f'color: {color_map[code]}')
            elif code in bg_color_map:  # Background colors
                styles.append(f'background-color: {bg_color_map[code]}')
        
        if styles:
            return f'<span style="{"; ".join(styles)}">'
        return ''
    
    # Match ANSI escape sequences: \033[...m or \x1b[...m
    ansi_pattern = r'\033\[([0-9;]*)m|\x1b\[([0-9;]*)m'
    html_text = re.sub(ansi_pattern, lambda m: replace_ansi(m), text)
    
    # Wrap in pre tag to preserve formatting and spacing
    return f'<pre style="background-color: #1e1e1e; color: #d4d4d4; padding: 10px; font-family: monospace;">{html_text}</pre>'
