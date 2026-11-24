
### Step 1: Create a GitHub Issue and Assign Yourself

Never start writing code, skills, or brain notes without an Issue (`Section 4`).

1. Go to the repository on GitHub and click the **Issues** tab.
2. Click **New issue** and pick the matching template (**Feature / Engineering Task** or **Defect / Bug Report**).
3. Fill in the title (e.g., `[TASK]: Add 10 research notes to Second Brain`) and the template fields (Requirement ID, description, acceptance criteria).
4. On the right sidebar, click **Assignees** $\rightarrow$ click **assign yourself**.
5. Add relevant **Labels** (e.g., `enhancement`, `documentation`, `bug`).
6. Click **Create** and note the Issue number (for example, `#4`).

---

### Step 2: Pull Latest `main` and Create a Feature Branch

Never work directly on `main` (it is protected and will reject direct pushes).

```bash
git checkout main
git pull origin main
git checkout -b <type>/<issue-number>-<short-description>

```

**Branch Naming Examples:**

* `feat/4-brain-ingest-skill` (new feature or skill)
* `docs/5-second-brain-research-notes` (brain notes, SRS, ADRs)
* `fix/9-quota-overflow-bug` (bug fix)
* `ci/1-github-actions-pipeline` (CI/CD workflows)
* `chore/2-issue-templates` (repo housekeeping)

---

### Step 3: Make Changes, Stage, and Commit Using Conventional Commits

After editing or adding files, check what changed:

```bash
git status

```

Stage only the files relevant to your task (avoid blindly adding temporary/unrelated files):

```bash
git add path/to/file1 path/to/file2
# Or to stage everything tracked/untracked in your working tree:
git add .

```

Commit using the **Conventional Commits** format:

```text
<type>(<optional-scope>): <short imperative summary>

```

| Prefix | When to Use It | Example Commit Message |
| --- | --- | --- |
| **`feat`** | New code feature, MCP tool, or Agent Skill | `feat(skills): add brain-ingest SKILL.md` |
| **`fix`** | Fixing a bug or broken link/schema | `fix(brain): repair broken wikilink in quota note` |
| **`docs`** | Second Brain notes, SRS, ADRs, `AGENTS.md`, README | `docs(brain): ingest YouTube API quota research note` |
| **`test`** | Adding or updating `pytest` unit/integration/regression tests | `test(quota): add pre-flight budget rejection test` |
| **`ci`** | Changes to `.github/workflows/` or CI validation scripts | `ci: add SKILL.md and brain wikilink validators` |
| **`chore`** | Repo config, `.gitignore`, dependencies, templates | `chore: add GitHub issue templates` |
| **`refactor`** | Restructuring code without changing external behavior | `refactor(provider): extract YouTubeProvider base class` |

Make small, meaningful commits as you work (`Section 4`):

```bash
git commit -m "docs(brain): add PARA folder structure and index.md"

```

---

### Step 4: Push Your Branch to GitHub

Push your local branch to the remote repository:

```bash
git push -u origin <your-branch-name>

```

*(If you make more commits on the same branch later, just run `git push`.)*

---

### Step 5: Open a Pull Request (PR) and Link the Issue

1. Open the repository on GitHub; you will see a yellow banner with a **Compare & pull request** button for your branch—click it.
2. Make sure the base branch is `main` and the compare branch is your feature branch.
3. Give the PR a clear title (e.g., `docs(brain): set up PARA vault and AGENTS.md`).
4. In the **Description**, summarize what changed and **include the auto-close keyword** for your Issue:
```markdown
### Summary
- Created PARA folders under `brain/` with `index.md` and `log.md`.
- Added root `AGENTS.md` with vault and security rules.

Closes #4

```


5. On the right sidebar, under **Reviewers**, assign at least one teammate to review your PR (`SB-5`, `Section 4`).


6. Click **Create pull request**.

---

### Step 6: Watch the CI Pipeline

Immediately after opening the PR, scroll to the bottom of the PR page to watch the **Checks** section:

* **`Build, Lint & Test`** — runs `pip install`, `ruff check .`, and `pytest`.


* **`Validate Skills & Brain`** — checks every `SKILL.md` frontmatter/naming and every `brain/` note's YAML schema and `[[wikilinks]]`.


* **`Secret Scanning`** — scans commits for accidental API keys or tokens.



**If a check turns red (❌):**

1. Click **Details** next to the failed check to read the exact error (e.g., missing `tags` field in a brain note, a typo in `[[wikilink]]`, or a `ruff` lint error).
2. Fix the issue locally on the **same branch**, commit, and push:
```bash
git add .
git commit -m "fix(brain): add missing author frontmatter field"
git push

```


3. CI will automatically re-run until all checks turn green (✅).

---

### Step 7: Peer Review, Merge, and Automatic Issue Closure

**For the Reviewer (Teammate):**

1. Open the PR and click the **Files changed** tab.
2. Read every line—especially AI-generated code or notes (`Section 6`).


3. Click **Review changes** (top right):
* Select **Request changes** if something needs fixing.
* Select **Approve** and click **Submit review** once everything looks good and CI is green.



**Merging & Cleanup:**

1. Once CI is green (✅) and at least **1 teammate has approved**, click **Merge pull request** $\rightarrow$ **Confirm merge**.
2. Because the PR description included `Closes #4`, GitHub **automatically closes Issue `#4**` and links it permanently to the merged PR.
3. Click **Delete branch** on GitHub to keep the repo tidy, then sync locally:
```bash
git checkout main
git pull origin main
git branch -d <your-branch-name>

```
