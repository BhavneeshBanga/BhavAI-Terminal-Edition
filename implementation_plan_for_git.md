Initialize Git Automatically on File Read/Write Operations
The user wants BhavAI to initialize Git in the workspace (CWD) whenever it reads or writes files. This will allow the user to easily track any modifications made by the agent in a standard red/green diff format (e.g., using git diff).

User Review Required
IMPORTANT

We will automatically set a local git config user.name as BhavAI and user.email as bhavai@local.ai to ensure that committing existing files does not fail due to missing identity configuration on the host system.
To avoid tracking Python compilation caches, test caches, local agent logs, and secret .env files, we propose creating a default .gitignore file during git initialization if one does not already exist.
Open Questions
TIP

Do you have any specific files or directories you want to exclude from git tracking besides the standard ones? We propose the following default .gitignore if none is present:

gitignore

__pycache__/
*.py[cod]
.pytest_cache/
.bhavai/
.env
Proposed Changes
Core Library
[MODIFY] 
tools.py
Add an ensure_git_initialized() helper function.
This function will:
Check if .git folder exists in CWD. If yes, return immediately.
Create a default .gitignore in CWD if .gitignore does not exist.
Run git init.
Run git config user.name "BhavAI" and git config user.email "bhavai@local.ai" (local configuration).
Stage all existing files using git add ..
Commit existing files using git commit --allow-empty -m "Initial commit before BhavAI execution".
Invoke ensure_git_initialized() at the beginning of:
read_file(path: str)
write_file(path: str, content: str)
update_file(path: str, content: str, mode: str)
Verification Plan
Automated Tests
Run pytest or python -m pytest to execute the existing tests.
Add a new test in 
test_tools.py
 verifying ensure_git_initialized behavior:
It creates .git directory under mock CWD.
It creates .gitignore if not present.
It successfully commits files.
Manual Verification
Run bhav wake up.
Give a file modification task.
Observe if git is initialized and changes are visible via git status or git diff.