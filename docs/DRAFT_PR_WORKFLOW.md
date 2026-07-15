# Verify a disposable draft pull request

Use this workflow to test CodeTrust against a real GitHub pull request without merging it.

## 1. Create a test branch

Start from current main branch:

```bash
git switch main
git pull --ff-only
git switch -c test/codetrust-verdict
```

Make one intentionally risky change. CodeTrust will learn baseline from base repository code, docs, tests, and structure. Pull-request author text describes proposed change but never establishes baseline.

## 2. Commit locally

```bash
git add path/to/changed-file
git commit -m "Test CodeTrust verdict"
```

Nothing reaches GitHub yet.

## 3. Push only when ready

```bash
git push -u origin test/codetrust-verdict
```

## 4. Open draft PR

```bash
gh pr create --draft \
  --base main \
  --head test/codetrust-verdict \
  --title "Test CodeTrust verdict" \
  --body-file path/to/pr-description.md
```

Copy returned PR URL.

## 5. Run CodeTrust

1. Start CodeTrust with `python3 start.py`.
2. Open <http://127.0.0.1:8787>.
3. Paste draft PR URL.
4. Confirm provider status says configured. Website model synthesis is required.
5. Select **Verify pull request**.
6. Review repository baseline, PR difference, scope distance, evidence paths, and technical findings.

## 6. Close disposable PR

CodeTrust never closes or merges pull requests. Close it explicitly:

```bash
gh pr close PR_NUMBER --delete-branch
```

Return local repository to main:

```bash
git switch main
git branch -D test/codetrust-verdict
```

Only delete local test branch after confirming no wanted work remains.
