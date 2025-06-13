"""Pydantic models for ontoeval data structures."""

from abc import ABC
from typing import Any, List, Optional
from datetime import datetime
from pydantic import BaseModel, Field, HttpUrl, ConfigDict, field_serializer

Change = tuple[int, str]

class Comparison(BaseModel):
    """A comparison between two PRs."""

    similarity: float = Field(..., description="Similarity score between 0 and 1")

class GitHubComment(BaseModel):
    """A comment on a GitHub issue or PR."""
    @field_serializer('created_at',)
    def serialize_datetime(self, dt: datetime) -> str:
        return dt.isoformat()
    
    id: str = Field(..., description="Comment ID")
    author: str = Field(..., description="Comment author username")
    body: str = Field(..., description="Comment body/content")
    created_at: datetime = Field(..., description="When the comment was created")
    url: str = Field(..., description="URL to the comment")


class GitHubItem(BaseModel, ABC):
    """Base class for GitHub items (Issues and PRs) with common metadata."""
    
    @field_serializer('created_at', 'updated_at')
    def serialize_datetime(self, dt: datetime) -> str:
        return dt.isoformat()
    
    number: int = Field(..., description="Item number")
    title: str = Field(..., description="Item title")
    body: Optional[str] = Field(None, description="Item body/description")
    url: str = Field(..., description="GitHub URL of the item")
    state: str = Field(..., description="Item state")
    author: str = Field(..., description="Item author username")
    created_at: datetime = Field(..., description="When the item was created")
    updated_at: datetime = Field(..., description="When the item was last updated")
    labels: List[str] = Field(default_factory=list, description="Item labels")
    comments: List[GitHubComment] = Field(default_factory=list, description="All comments on this item")
    assignees: Any | None = Field(None, description="List of assignees for the PR")
    
    def get_comment_count(self) -> int:
        """Get total number of comments."""
        return len(self.comments)
    
    def get_authors(self) -> List[str]:
        """Get all unique authors (item author + comment authors)."""
        authors = {self.author}
        authors.update(comment.author for comment in self.comments)
        return sorted(list(authors))
    
    def get_comment_text(self) -> str:
        """Get all comment text concatenated."""
        return "\n\n".join(comment.body for comment in self.comments)


class GitHubIssue(GitHubItem):
    """GitHub issue linked to a PR.
    
    Note that the overall data model is PR-centric, all issues are nested inside PRs, and we are
    not concerned with other issues.
    """
    
    def is_new_term_request(self) -> bool:
        """Check if this issue is a new term request based on labels."""
        ntr_labels = ['new term request', 'NTR', 'term request', 'new-term-request']
        return any(label.lower() in [l.lower() for l in ntr_labels] for label in self.labels)


class PRBenchmark(GitHubItem):
    """Benchmark data extracted from a GitHub pull request."""
    
    repo: str = Field(..., description="GitHub repository in format 'owner/name'")
    pr_number: int = Field(..., description="Pull request number (same as number field)")
    head_commit: str = Field(..., description="SHA of the head commit (after changes)")
    base_commit: str = Field(..., description="SHA of the base commit (before changes)")
    files_changed: List[str] = Field(default_factory=list, description="List of file paths that were changed")
    commits: List[str] = Field(default_factory=list, description="List of commit messages in the PR")
    diff: str | None = Field(None, description="Full diff content of the pull request (this is the ground truth diff, from the curators)")
    diff_size_chars: int | None = Field(None, description="Size of the diff in characters")
    diff_size_lines: int | None = Field(None, description="Size of the diff in lines")
    linked_issues: List[GitHubIssue] = Field(default_factory=list, description="GitHub issues linked to this PR")
    part_of_epic: bool | None = Field(None, description="Whether this PR is linked to an issue that has other PRs")
    input_text: str | None = Field(None, description="Text to be provided as input prompt to test the AI agent")
    issue_labels: list[str] | None = Field(None, description="Labels of the linked issues")

    experiment_id: str | None = Field(None, description="E.g. uberon-1")
    experiment_title: str | None = Field(None, description="E.g. uberon with goose+o3")

    agent_stdout: str | None = Field(None, description="Standard output from the agent")
    agent_stderr: str | None = Field(None, description="Standard error from the agent")
    predicted_diff: str | None = Field(None, description="Predicted diff content of the pull request (this is the output of the agent)")
    predicted_diff_identical: bool | None = Field(None, description="Whether the predicted diff is identical to the target diff")

    # fields populated after running the agent - TODO: deprecate in favor of composition
    predicted_diff_metadiff: list[str] | None = Field(None, description="Metadata diff between the predicted and target diff")
    predicted_diff_similarity: float | None = Field(None, description="Similarity between the predicted and target diff")
    predicted_diff_changes_in_common: list[Change] | None = Field(None, description="Changes between the predicted and target diff")
    changes_unique_to_target: list[Change] | None = Field(None, description="Changes in the predicted diff that are not in the target diff")
    changes_unique_to_prediction: list[Change] | None = Field(None, description="Changes in the target diff that are not in the predicted diff")

    comparisons: dict[str, Comparison] | None = Field(None, description="Comparisons with other PRs, keyed by judge name")

    def __init__(self, **data):
        # Ensure pr_number matches number
        if 'pr_number' in data and 'number' not in data:
            data['number'] = data['pr_number']
        elif 'number' in data and 'pr_number' not in data:
            data['pr_number'] = data['number']
        super().__init__(**data)
        
    def has_ontology_changes(self) -> bool:
        """Check if this PR contains ontology file changes."""
        ontology_patterns = ['-edit.obo', '-edit.owl', '.obo', '.owl']
        return any(
            any(pattern in file_path for pattern in ontology_patterns)
            for file_path in self.files_changed
        )
        
    def is_term_addition(self) -> bool:
        """Check if this PR appears to add new ontology terms."""
        return '[Term]' in self.diff and 'id: ' in self.diff
        
    def get_added_term_ids(self) -> List[str]:
        """Extract new term IDs from the diff (basic heuristic)."""
        term_ids = []
        lines = self.diff.split('\n')
        in_new_term = False
        
        for line in lines:
            if line.startswith('+[Term]'):
                in_new_term = True
            elif line.startswith('+id: ') and in_new_term:
                term_id = line.replace('+id: ', '').strip()
                term_ids.append(term_id)
                in_new_term = False
        
        return term_ids
    
    def get_linked_issue_numbers(self) -> List[int]:
        """Get list of linked issue numbers."""
        return [issue.number for issue in self.linked_issues]
    
    def has_new_term_request_labels(self) -> bool:
        """Check if any linked issues have new term request labels."""
        return any(issue.is_new_term_request() for issue in self.linked_issues)
    
    def get_all_discussion_text(self) -> str:
        """Get all text from PR and linked issues (body + comments)."""
        all_text = []
        
        # PR body and comments
        if self.body:
            all_text.append(f"PR Body:\n{self.body}")
        if self.comments:
            all_text.append(f"PR Comments:\n{self.get_comment_text()}")
            
        # Linked issues body and comments
        for issue in self.linked_issues:
            if issue.body:
                all_text.append(f"Issue #{issue.number} Body:\n{issue.body}")
            if issue.comments:
                all_text.append(f"Issue #{issue.number} Comments:\n{issue.get_comment_text()}")
        
        return "\n\n" + "="*50 + "\n\n".join(all_text)
    
    def populate_derived_fields(self) -> None:
        """Populate derived fields."""
        self.diff_size_chars = len(self.diff) if self.diff else 0
        self.diff_size_lines = len(self.diff.splitlines()) if self.diff else 0
        self.issue_labels = []
        for issue in self.linked_issues:
            self.issue_labels.extend(issue.labels)
    
    def calculate_input_text(self, exclude_post_pr_comments: bool = True) -> None:
        """Populate the input_text field with the PR body and linked issues body and comments."""
        date_cutoff=self.created_at
        excluded = False
        all_text = []
        for issue in self.linked_issues:
            if issue.created_at > date_cutoff:
                excluded = True
                break
            
            all_text.append(f"## Issue {issue.number}\nAuthor: {issue.author}\nBody:\n<body>\n{issue.body}\n</body>")
            if issue.comments:
                for comment in issue.comments:
                    if comment.created_at >= date_cutoff and exclude_post_pr_comments:
                        break
                    all_text.append(f"Comment:\nAuthor: {comment.author}\n<comment>\n{comment.body}\n</comment>")
        if excluded:
            return
        return "\n\n".join(all_text)

    def populate_input_text(self,) -> None:
        """Populate the input_text field with the PR body and linked issues body and comments."""
        self.input_text = self.calculate_input_text(exclude_post_pr_comments=True)
