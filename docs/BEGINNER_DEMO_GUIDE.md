# CodeTrust beginner demo and recording guide

This guide explains exactly what to open, what to paste, what result to expect, and what to say while recording.

Everything in this guide belongs to the private `JadeBear-09/codetrust-agent` repository. No files or changes are written to the public GnuCash repository.

## First: repo versus pull request

- **Repository:** complete project and its files.
- **Pull request (PR):** proposed change to a repository.
- **What CodeTrust needs:** PR URL only.
- **Why repository link is listed:** to show viewers where project lives. Do not paste repository URL into CodeTrust.

## Start CodeTrust

Open Terminal and run:

```bash
cd "/Users/beebee/Documents/dtdl agent"
python3 start.py
```

Open [http://127.0.0.1:8787](http://127.0.0.1:8787).

If private GitHub PR fails to load, authenticate once:

```bash
gh auth login
```

## Demo 1: public GnuCash PR rejected by maintainer

### Links

- Main repository: <https://github.com/Gnucash/gnucash>
- Pull request to paste into CodeTrust: <https://github.com/Gnucash/gnucash/pull/2262>
- Maintainer decision to reveal after CodeTrust verdict: <https://github.com/Gnucash/gnucash/pull/2262#issuecomment-4887262599>

### What to paste

Paste this into **GitHub pull request**:

```text
https://github.com/Gnucash/gnucash/pull/2262
```

Paste this into **Approved intent**:

```markdown
# GnuCash appearance policy

## Outcome
Preserve appearance configuration through the supported GTK3 theme system.

## In scope
- GTK3 theme configuration controls light and dark appearance.

## Out of scope
- Application-level configurable light and dark appearance mode.
- GnuCash preferences that override GTK3 theme behavior.

## Acceptance criteria
- Users configure appearance through GTK3 themes, not application settings.
```

Keep **Use configured model for synthesis** checked. Select **Verify pull request**.

### Expected result

- Verdict: `BLOCK`
- Risk score: `100/100`
- Changed files: `14`
- Scope drift: `50%`
- Evidence-backed findings: `8`

Then open maintainer decision. PR is closed without merge. Maintainer says change is out of scope and appearance should use a GTK3 theme.

### Honest narration

> This is a real public pull request. I supplied the approved product boundary and kept the maintainer outcome hidden. CodeTrust fetched the live diff and blocked the change because eight changed surfaces crossed that boundary. Now I reveal the recorded maintainer decision: the PR was closed unmerged as out of scope. CodeTrust's policy verdict matched the maintainer decision.

Do not say CodeTrust blindly predicted every maintainer decision. This demo proves one external policy-alignment match.

## Demo 2: private CodeTrust payment PR

### Links

- Main private repository: <https://github.com/JadeBear-09/codetrust-agent>
- Pull request to paste into CodeTrust: <https://github.com/JadeBear-09/codetrust-agent/pull/2>

### What to paste

Paste this into **GitHub pull request**:

```text
https://github.com/JadeBear-09/codetrust-agent/pull/2
```

Leave **Approved intent** blank. CodeTrust uses PR title and description. Keep model checkbox checked. Select **Verify pull request**.

### Expected result

- Verdict: `BLOCK`
- Risk score: `94/100`
- Changed files: `5`
- Evidence-backed findings: `4`

Main findings:

1. Retried payment action lacks idempotency evidence.
2. Blocking synchronous network request appears inside an async path.
3. Database schema change lacks rollback.
4. Risk-sensitive change lacks failure-path tests.

### Narration

> This second PR is from my private CodeTrust repository. CodeTrust uses its real PR description as intent, fetches the live diff, and returns BLOCK 94 out of 100. It shows exact file and line evidence, business impact, and suggested verification. Model explains findings, but deterministic gates control the verdict.

## Close the private test PR after recording

GitHub calls this **Close pull request**, not cancel.

In browser:

1. Open <https://github.com/JadeBear-09/codetrust-agent/pull/2>.
2. Scroll to bottom.
3. Select **Close pull request**.
4. Do not select merge.

Or use Terminal:

```bash
gh pr close 2 --repo JadeBear-09/codetrust-agent
```

CodeTrust intentionally never merges or closes a PR.

## Recording order

1. Show CodeTrust home screen.
2. Run public GnuCash PR.
3. Show `BLOCK 100/100` and two or three exact findings.
4. Reveal public maintainer rejection.
5. Run private CodeTrust PR.
6. Show `BLOCK 94/100` and four technical findings.
7. End with human boundary: CodeTrust verifies; human decides.

## Final claim

Use this sentence:

> CodeTrust turns approved intent and live pull-request changes into evidence-backed verdicts. It never merges code, and it never lets model confidence overwrite deterministic evidence.
