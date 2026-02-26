---
name: review-pr
description: Review PR comments from GitHub Copilot or other reviewers. Fetches comments, reads referenced code, classifies each as AGREE/UNNECESSARY/DISAGREE, and produces a prioritized list of changes to implement.
argument-hint: "[PR number or blank for current branch]"
---

# PR Review

Review PR comments from GitHub Copilot, Claude Code Review, or other reviewers. Follow these steps:

## 1. CONTEXT GATHERING
- Verify the current git branch: `git branch --show-current`
- Identify what branch this PR is merging into (ask if not provided)

## 2. AUTO-FETCH PR COMMENTS
- Find the PR for the current branch:
  ```
  gh pr list --head $(git branch --show-current) --json number,title,url --limit 1
  ```
- If `$ARGUMENTS` provides a PR number, use that instead.
- If a PR is found, fetch all review comments (inline code review comments from Copilot, SonarQube, human reviewers, etc.):
  ```
  gh api repos/{owner}/{repo}/pulls/{pr_number}/comments --jq '.[] | "FILE: \(.path):\(.line) // \(.original_line)\nREVIEWER: \(.user.login)\nBODY: \(.body)\n---"'
  ```
- Also fetch top-level PR review comments (non-inline):
  ```
  gh api repos/{owner}/{repo}/pulls/{pr_number}/reviews --jq '.[] | select(.body | length > 0) | {reviewer: .user.login, state: .state, body: .body}'
  ```
- Also fetch issue-level comments (general PR discussion):
  ```
  gh pr view {pr_number} --comments --json comments --jq '.comments[] | "REVIEWER: \(.author.login)\nBODY: \(.body)\n---"'
  ```
- Present all fetched comments to the user in a clear summary before proceeding with analysis.
- **COUNT VERIFICATION:** After fetching, count the total number of reviewer comments (excluding your own replies). State the count explicitly: "Found N comments to review." If the final review count doesn't match, you missed one -- go back and find it.
- If no PR is found for the current branch, ask the user to provide the PR number or paste comments manually. Merge them with the auto-fetched ones.
- The user may also provide additional comments manually; merge them with the auto-fetched ones.

## 3. Read the file(s) referenced in the comments to understand current implementation.

## 4. For EACH comment, perform a critical analysis:
a) Read the referenced code in our codebase
b) Understand what the comment is suggesting and why
c) Evaluate against our actual implementation and codebase patterns
d) Classify into one of three categories: AGREE, UNNECESSARY, or DISAGREE

## 5. For each classification, provide the following:

### ==IF YOU AGREE==
- State WHY you agree with the comment
- Review the proposed changes from the reviewer
- Either:
  - Propose the SAME change if it's correct, OR
  - Propose a MODIFIED version that better fits our codebase patterns
  - Explain any modifications and why they're better while still addressing the core issue
- Provide the exact code change to implement

### ==IF THE CHANGE IS UNNECESSARY==
- State WHY the change is unnecessary
- Show HOW our code already handles the concern, OR
- Explain WHY the suggested change isn't needed in our context
- Reference specific lines/logic that make this unnecessary

### ==IF YOU DISAGREE==
- State WHY you disagree
- Illustrate with specific code/logic from our implementation that proves your point
- Assign a CONFIDENCE SCORE (Low/Medium/High) based on:
  - Low: The suggestion has some merit but adds unnecessary complexity
  - Medium: The suggestion misunderstands our implementation but has a valid concern
  - High: The suggestion is fundamentally incorrect or would break functionality
- Explain what would happen if we implemented the suggestion (if problematic)

## 6. After reviewing all comments, provide a SUMMARY:
- Total comments reviewed
- Breakdown: X agreed, Y unnecessary, Z disagreed
- Prioritized list of changes to implement (if any)
- Any comments that need further discussion with the team

## IMPORTANT GUIDELINES
- Be critical but fair -- don't dismiss comments without solid reasoning
- Consider edge cases the reviewer might have identified that we missed
- Our codebase patterns and context matter -- a generic suggestion may not apply
- If a suggestion improves safety/robustness without significant cost, lean toward agreeing
- Never implement changes blindly -- always verify against our actual code first
- After analysis, ask the user which changes to implement before making any code modifications
