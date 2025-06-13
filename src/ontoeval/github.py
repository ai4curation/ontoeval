from collections import defaultdict
import subprocess
import json
import re
import diskcache as dc

from typing import List
from .models import PRBenchmark, GitHubIssue, GitHubComment

# Create a cache directory
cache = dc.Cache('./.cache')

def get_comments(repo: str, item_type: str, item_number: int) -> List[GitHubComment]:
    """
    Get all comments for a GitHub issue or PR.
    
    Args:
        repo: GitHub repo in format "owner/name"
        item_type: "issue" or "pr"
        item_number: Issue or PR number
        
    Returns:
        List of GitHubComment objects

    Example:
        >>> cmts = get_comments("geneontology/go-ontology", "pr", 13123)
        >>> len(cmts)
        7

    """
    result = subprocess.run([
        'gh', item_type, 'view', str(item_number),
        '--repo', repo,
        '--json', 'comments'
    ], capture_output=True, text=True, check=True)
    
    data = json.loads(result.stdout)
    comments = []
    
    for comment_data in data.get('comments', []):
        comment = GitHubComment(
            id=comment_data['id'],
            author=comment_data['author']['login'],
            body=comment_data['body'],
            created_at=comment_data['createdAt'],
            updated_at=comment_data.get('updatedAt'),
            url=comment_data['url']
        )
        comments.append(comment)
        
    return comments


def extract_issue_numbers_from_text(text: str) -> List[int]:
    """
    Extract GitHub issue numbers from text using common patterns.

    Args:
        text: Text to extract issue numbers from
    
    Returns:
        List of issue numbers
    
    Example:
        >>> extract_issue_numbers_from_text("fixes #123")
        [123]

        >>> extract_issue_numbers_from_text("closes #456")
        [456]

        >>> extract_issue_numbers_from_text("resolves #789")
        [789]

        >>> extract_issue_numbers_from_text("Issue 12349")
        [12349]
    
    Looks for patterns like:
    - fixes #123
    - closes #456  
    - resolves #789
    - #123 (standalone)
    """
    if not text:
        return []
    
    # Common GitHub issue linking patterns
    patterns = [
        r'(?:fix(?:es)?|close(?:s)?|resolve(?:s)?)\s+#(\d+)',  # fixes #123
        r'(?:^|[^#])#(\d+)(?![#\d])',  # standalone #123
        r'(?:^|[^#])issue\s+(\d+)(?![#\d])',  # standalone 'Issue 12349'
    ]
    
    issue_numbers = set()
    for pattern in patterns:
        matches = re.findall(pattern, text, re.IGNORECASE | re.MULTILINE)
        issue_numbers.update(int(match) for match in matches)
    
    return sorted(list(issue_numbers))


def get_issue_info(repo: str, issue_number: int) -> GitHubIssue:
    """
    Get comprehensive information about a specific GitHub issue.
    
    Args:
        repo: GitHub repo in format "owner/name"
        issue_number: Issue number to fetch
        
    Returns:
        GitHubIssue model with complete issue data including comments
    """
    result = subprocess.run([
        'gh', 'issue', 'view', str(issue_number),
        '--repo', repo,
        '--json', 'number,title,body,url,state,labels,author,createdAt,updatedAt'
    ], capture_output=True, text=True, check=True)
    
    issue_data = json.loads(result.stdout)
    
    # Get all comments for this issue
    comments = get_comments(repo, 'issue', issue_number)
    
    return GitHubIssue(
        number=issue_data['number'],
        title=issue_data['title'],
        body=issue_data.get('body'),
        url=issue_data['url'],
        state=issue_data['state'],
        author=issue_data['author']['login'],
        created_at=issue_data['createdAt'],
        updated_at=issue_data['updatedAt'],
        labels=[label['name'] for label in issue_data['labels']],
        comments=comments
    )


def get_pr_list(repo: str, state: str = "all", limit: int = 100, from_pr: int | None = None) -> List[int]:
    """
    Get list of PR numbers from a repository.

    Args:
        repo: GitHub repo in format "owner/name"
        state: PR state - "open", "closed", "merged", or "all"
        limit: Maximum number of PRs to return
        from_pr: Start from this PR number (note that we are working backwards from most recent PR)

    Returns:
        List of PR numbers

    Example:
        >>> pr_numbers = get_pr_list("geneontology/go-ontology")
        >>> len(pr_numbers)
        100

        >>> pr_numbers = get_pr_list("geneontology/go-ontology", state="open", limit=10)
        >>> len(pr_numbers)
        10

        >>> pr_numbers = get_pr_list("geneontology/go-ontology", state="merged", limit=1, from_pr=30355)
        >>> pr_numbers
        [30355]
    
    """
    if from_pr:
        all_prs = all_repo_prs(repo, state=state)
        #print(f"🔍 Found {len(all_prs)} PRs in {repo}")
        return [pr for pr in all_prs if pr <= from_pr][:limit]
    
    cmd =[
        'gh', 'pr', 'list',
        '--repo', repo,
        '--state', state,
        '--limit', str(limit),
        '--json', 'number'
    ]
    result = subprocess.run(cmd , capture_output=True, text=True, check=True)
    
    pr_data = json.loads(result.stdout)
    return [pr['number'] for pr in pr_data]

@cache.memoize()
def all_repo_prs(repo: str, state: str = "merged", limit: int = 1000000) -> List[int]:
    """
    Get all PR numbers from a repository.

    This will be slow the first time

    """
    return get_pr_list(repo, state=state, limit=limit)

@cache.memoize()
def analyze_pr(repo: str, pr_number: int) -> PRBenchmark:
    """
    Analyze a GitHub PR to extract benchmark data.
    
    Args:
        repo: GitHub repo in format "owner/name" (e.g. "geneontology/go-ontology")
        pr_number: PR number to analyze
        
    Returns:
        PRBenchmark model with PR metadata, commits, and file changes
    """
    # Get PR metadata
    pr_result = subprocess.run([
        'gh', 'pr', 'view', str(pr_number),
        '--repo', repo, 
        '--json', 'url,number,title,body,headRefOid,baseRefOid,files,commits,author,createdAt,updatedAt,state,labels'
    ], capture_output=True, text=True, check=True)
    
    pr_data = json.loads(pr_result.stdout)
    
    # Get the actual diff
    try:
        diff_result = subprocess.run([
            'gh', 'pr', 'diff', str(pr_number),
                '--repo', repo
            ], capture_output=True, text=True, check=True)
    except subprocess.CalledProcessError:
        # if the diff is too large, gh will fail with a 400 error
        diff_result = None
    
    # Get all comments for this PR
    pr_comments = get_comments(repo, 'pr', pr_number)
    
    # Extract linked issues from PR body, title, and commits
    all_text = f"{pr_data['title']} {pr_data['body'] or ''}"
    for commit in pr_data['commits']:
        all_text += f" {commit['messageHeadline']}"
    
    issue_numbers = extract_issue_numbers_from_text(all_text)
    
    # Fetch issue information
    linked_issues = []
    for issue_num in issue_numbers:
        try:
            issue = get_issue_info(repo, issue_num)
            linked_issues.append(issue)
        except subprocess.CalledProcessError:
            # Issue might not exist or be inaccessible, skip it
            continue
    
    pr_files = pr_data.get('files')
    if not pr_files:
        pr_files = []
    pr = PRBenchmark(
        repo=repo,
        pr_number=pr_number,
        number=pr_number,
        title=pr_data['title'],
        body=pr_data['body'],
        url=pr_data['url'],
        state=pr_data['state'],
        author=pr_data['author']['login'],
        created_at=pr_data['createdAt'],
        updated_at=pr_data['updatedAt'],
        labels=[label['name'] for label in pr_data.get('labels', [])],
        comments=pr_comments,
        head_commit=pr_data['headRefOid'],
        base_commit=pr_data['baseRefOid'], 
        files_changed=[f['path'] for f in pr_files],
        commits=[c['messageHeadline'] for c in pr_data['commits']],
        diff=diff_result.stdout if diff_result else None,
        linked_issues=linked_issues
    )
    pr.populate_input_text()
    return pr


def check_for_epics(prs: list[PRBenchmark | dict]) -> list[str]:
    """
    Check for epics in a list of PRs.

    Here an epic is defined as a PR that is linked to an issue that has other PRs.

    Args:
        prs: List of PRs to check

    Returns:
        List of PRs that are part of an epic
    """
    issue_to_prs = defaultdict(set)
    prs = [pr.model_dump()  if isinstance(pr, PRBenchmark) else pr for pr in prs]
    for pr in prs:
        for issue in pr.get("linked_issues", []):
            issue_to_prs[issue.get("number")].add(pr.get("pr_number"))
    
    part_of_epics = []
    for pr in prs:
        linked_issues = pr.get("linked_issues", [])
        for issue in linked_issues:
            if len(issue_to_prs[issue.get("number")]) > 1:
                part_of_epics.append(pr.get("pr_number"))
                break
            
    return part_of_epics