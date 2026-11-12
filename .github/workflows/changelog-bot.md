---
# Biweekly changelog PR bot (GitHub Agentic Workflow).
#
# This is the gh-aw SOURCE file. After editing, regenerate the compiled
# GitHub Actions workflow with:
#
#     gh aw compile changelog-bot
#
# and commit the generated `.github/workflows/changelog-bot.lock.yml` alongside it.

on:
  # Cron cannot express "every other Saturday", so we fire every Saturday at
  # around 12:00 UTC and the prompt gates on ISO-week parity (see the body below).
  schedule: weekly on saturday around 12:00 UTC
  # Allow maintainers to trigger a run on demand (ignores the biweekly gate).
  workflow_dispatch:

permissions:
  contents: read

# The default checkout is shallow (fetch-depth 1) with no tags, which makes the
# agent see only the latest commit. Fetch full history so it can scan the
# commit window and read the commit log. A second checkout
# fetches the documentation repo (all branches) for the shared release-notes PR.
checkout:
  - fetch-depth: 0
  - repository: canonical/landscape-documentation
    path: ./landscape-documentation
    fetch: ["*"]
    # Contents-read on the docs repo is enough: this token only fetches refs
    # at setup time.
    github-token: ${{ secrets.LANDSCAPE_DOCS_TOKEN }}

engine:
  id: copilot
  model: sonnet

# Only the shell commands the agent needs to inspect history and format dates.
tools:
  bash:
    - "git"
    - "date"
    - "safeoutputs"
  edit:

# The agent never pushes directly; its file edits are turned into pull
# requests. The own-repo changelog PR uses the default GITHUB_TOKEN (like
# landscape-server's merged bot). The docs push handler uses
# LANDSCAPE_DOCS_TOKEN, a PAT with contents+pull-requests write on
# canonical/landscape-documentation.
safe-outputs:
  create-pull-request:
    title-prefix: "build: "
    labels: [changelog, automation]
    team-reviewers: [canonical/landscape]
    draft: false
    if-no-changes: ignore
    preserve-branch-name: true
    recreate-ref: true
    # The bot only ever edits CHANGELOG.md in this repository; the handler
    # rejects any other path outright. Release-notes pages live in the docs
    # repo and are only ever touched via push-to-pull-request-branch below.
    allowed-files: ["CHANGELOG.md"]
    # Unlike landscape-ui there is no changeset directory to opt out of the
    # protected-file defaults and no generated changelog to strip: CHANGELOG.md
    # is the bot's target file, and there are no version bumps (charm revisions
    # are assigned by the Charmhub release automation at publish time). gh-aw
    # allowed-files filters by path only, so the "insert a new section, never
    # rewrite existing content" rule is enforced by the prompt, not the
    # handler.
  push-to-pull-request-branch:
    target: "*"
    target-repo: canonical/landscape-documentation
    github-token: ${{ secrets.LANDSCAPE_DOCS_TOKEN }}
    required-labels: [changelog, automation]
    # Docs PR updates may only touch release-notes pages (including index.md).
    allowed-files: ["docs/reference/release-notes/*.md"]
    max: 1
---

# Biweekly changelog update

You maintain the changelog for the Landscape Server charm (the Juju charm that deploys and manages Landscape Server). The changelog is `CHANGELOG.md` at the repository root: a newest-first list of dated sections that this bot creates and maintains — no other automation or convention touches it. Your job is to draft a new dated changelog section summarizing recent user-facing changes and open a pull request with it.

## Hard prohibitions

- In this repository, `CHANGELOG.md` is the ONLY file you may ever create or modify. This is mechanically enforced by the pull-request handler: every other path is rejected from any patch it delivers.
- NEVER edit or delete existing `CHANGELOG.md` content — only insert one new dated section directly under the header. Past sections are merged history. (The handler's file allowlist filters by path only, so this insert-only rule is enforced by you, not the handler.)
- NEVER touch release machinery: `charmcraft.yaml`, `metadata.yaml`, workflows, or any version file. Charm revisions are assigned by the Charmhub release automation at publish time; there is nothing to bump in this repository.
- These prohibitions apply to this repository (landscape-server-operator) only; editing the release-notes page in the separate docs checkout is expected and allowed.

## Biweekly gate

This workflow is scheduled every Saturday but should only act every **other** Saturday. Releases publish on **odd** ISO weeks.

This run was triggered by the `${{ github.event_name }}` event. Use that value literally to decide whether the gate applies:

1. If the triggering event is `workflow_dispatch`, always proceed regardless of the week number (manual runs bypass the biweekly gate entirely).
2. Otherwise (a `schedule` run), run `date +%V` to get the current ISO week number. If that week number is **even**, stop immediately and make no changes — do not open a pull request. Only proceed on **odd** weeks.

## Gather the commits

1. The changelog lives at `CHANGELOG.md` in the repository root. It may not exist yet; this bot creates it on the first run.
2. The scan window is time-based: list the commits from the last four weeks with `git log --since="4 weeks ago" --no-merges --pretty=%H%x09%s`. `main` is squash-merged, so each merged PR is a single commit on this list. NEVER anchor on tags: every push to `main` is published to Charmhub as a new charm revision and CI tags the commit `rev<N>`, so the newest tag sits at or near `HEAD` and a tag anchor would scan almost nothing — the tags mark publish points, not changelog coverage. Four weeks against a biweekly schedule gives two weeks of overlap with the previous run, so omissions leapfrogged by later merges are still caught; the deduplication rules below prevent double-filing.
3. Skip any commit whose subject has no trailing pull request reference ` (#1234)`. Such commits cannot carry the ` (#<N>)` marker the deduplication relies on, so they can never be filed safely; if one looks user-facing, mention it in the PR body under `Changelog entries to review` instead of filing it.
4. Deduplicate the rest by pull request number. For each commit, extract its PR number `<N>` from the trailing ` (#1234)` reference in the subject. Skip the commit if EITHER of the following holds:
   a. Its own commit added a NON-EMPTY changelog entry: run `git show --name-status --format= <commit>` and look for `M CHANGELOG.md`, then check `git show <commit> -- CHANGELOG.md` for at least one added bullet (a `+` line whose added text starts with `- `). Only added bullets count as coverage — a commit that modified `CHANGELOG.md` without adding a bullet (e.g. a typo fix) is NOT coverage. If a user-facing commit touched `CHANGELOG.md` but added no bullet, do NOT file an entry for it either: a commit that deliberately touched the changelog made its own changelog choice. Flag it in the review section below instead.
   b. The changelog already covers it: search the whole of `CHANGELOG.md` in the working tree for the exact reference `#<N>` (match the full number — `#123` must not match `#1234`). Every entry this bot files ends with ` (#<N>)`, so a hit means a merged pull request (this bot's or a maintainer's) already filed it. `CHANGELOG.md` on `main` reflects only merged pull requests: entries in a still-open bot PR are not in it, so they are collected again — the handler recreates the bot's branch from the current `main` tip, so the updated PR carries the full set of still-unfiled entries and nothing is lost.

## Select user-facing commits only

Include only commits that a Landscape administrator would notice. Commit subjects in this repo are usually conventional commits, but the type prefix is sometimes capitalized (e.g. `Fix:`) and occasionally missing entirely — match prefixes case-insensitively and use your judgment for non-conforming subjects.

- **Include**: `feat:`, `fix:`, `perf:`, and any breaking change (a `!` before the colon, e.g. `feat!:` / `fix!:`).
- **Maybe Include**: `refactor: ` commits, only if they are user-facing.
- **Exclude**: `chore:`, `ci:`, `test:`, `build:`, `docs:`, and `style:`, commits,
  plus anything that only touches tooling, tests, or CI, and any dependency bumps.

Breaking changes are not always flagged in the subject. For every selected commit, also inspect the full commit message with `git show -s --format=%B <sha>` and look for `BREAKING CHANGE:` or `BREAKING-CHANGE:` footers. A commit carrying such a footer is a breaking change even when its subject has no `!` — classify it as breaking and note the breaking nature in the docs island bullet.

For each selected commit, derive a one-line summary from its subject line. Proofread and correct any obvious spelling or grammar errors. Remove Jira issue references such as `LNDENG-5678` wherever they occur in the subject, and strip any trailing GitHub pull request reference such as ` (#1234)` — it is re-added as the coverage marker when the entry is composed below. Do **not** strip `(LP: #NNNN)` references. If there are no user-facing commits in the window at all, stop and make no changes.

## Sort the commits

Group the commits by their type. Adhere to the following order.

- Breaking changes (a `!` in the subject or a `BREAKING CHANGE:`/`BREAKING-CHANGE:` footer)
- `feat`
- `fix`
- `perf`
- `refactor`

Within each group, maintain the relative ordering of the commits. Use this ordering when listing the new entries in the pull request body.

## Compose the new section

Charm releases are Charmhub revisions assigned at publish time, not versions declared in this repository, so changelog sections are dated rather than versioned.

If `CHANGELOG.md` does not exist yet, create it with exactly this header:

```
# Changelog

All notable user-facing changes to this charm are documented here, newest first.
```

Insert a new dated section directly under that header, before any existing sections, so the file stays newest-first:

```
## YYYY-MM-DD

### Features

- <summary> (#1234)
```

- Use `date +%F` for the section date (e.g. `2026-11-10`).
- Group entries under headings in this order: `### Breaking changes`, `### Features`, `### Fixes`, `### Performance`, `### Refactors`. Omit headings that have no entries.
- Each entry is a bullet beginning with `- `. The `<summary>` is the single-line summary derived above: one capitalized sentence, no type prefix, no trailing period, no Jira references. There is one mandatory exception to "no PR references": end the entry with ` (#<N>)` naming the pull request the entry covers (e.g. `- Serve hostagent messenger over TLS via haproxy-route (#201)`). Later runs rely on this marker to recognize already-covered PRs.

## Review existing changelog entries

Commits in the window that already touched `CHANGELOG.md` made their own changelog choices. For each such commit, read the change and flag mismatches. Do NOT edit or delete existing entries — past sections are merged history. List flagged entries under a `Changelog entries to review` heading in the PR body, one bullet per PR with the reason and evidence (commit/PR links).

- **Changelog touched but no bullet added on a user-facing change**: the commit modified `CHANGELOG.md` without adding a bullet, but it matches "Select user-facing commits" (see rule 4a above). Propose an entry. If the change is only reachable in a non-default configuration, make this reasoning clear.
- **Changelog entry with no user impact**: the commit added a `CHANGELOG.md` bullet, but every path in `git show --name-only --format= <commit>` is a test (`tests/`), CI/tooling (`.github/`, root config files), or docs file.
- **Fix for an unreleased regression**: for a `fix:` commit F that added a changelog bullet, take the hunks F modified (`git show -U0 F`) and run `git blame --porcelain -L <start>,<end> F^ -- <file>` to find the commits that introduced those lines. If they all fall inside the window, the bug never shipped and the entry should be removed. A PR title or body that references another PR merged in the same window is supporting evidence. If blame results are mixed, mark the entry "possible", not certain.

Exclude flagged entries from the docs release-notes island. If a pull request is opened, list the flagged entries under a `Changelog entries to review` heading in its body, one bullet per PR with the reason and evidence (commit/PR links). If no pull request is opened (nothing to file), report the flagged entries in your run summary instead — do not open a pull request that contains no changes.

## Open the pull request

Open a single pull request with the new section. Use the title `changelog update for <date>` (the `build: ` prefix is added automatically) and a body that lists the new entries in the sorted order from above, notes the merged PR each entry covers, explains that only user-facing changes were selected, and includes the `Changelog entries to review` heading when any entries were flagged. If no entries were needed, do nothing — do not open an empty pull request.

## Docs release notes (shared PR)

You also maintain the user-facing release notes. All Landscape changelog bots share ONE pull request against `canonical/landscape-documentation` that drafts the release notes for the in-development Landscape release. That shared PR is created centrally: a scheduled `release-notes-draft` workflow in `canonical/landscape-documentation` opens it every week (Fridays around 12:00 UTC), based on the `develop` branch, and pre-seeds the release-notes page with every bot's island markers. No changelog bot ever creates it. Each bot owns exactly one marked section (island) in that PR. NEVER open a separate per-repo docs PR: find the shared PR and push to it.

The docs work happens in the separate `./landscape-documentation` checkout. The hard prohibitions above apply to this repository (landscape-server-operator) only; editing the release-notes page in the docs checkout is expected and allowed.

Your island content derives from ALL user-facing commits selected in the window above — not only the ones missing from `CHANGELOG.md`: a PR already filed in the changelog still belongs in the release notes. Rewrite those selected commits into docs-appropriate bullets, excluding any entries flagged in `Changelog entries to review`.

1. Determine the in-development Landscape release `YY.MM`: Landscape releases are `YY.04` and `YY.10`. From today's date, the in-development release is the next boundary strictly in the future (before April -> `YY.04`; before October -> `YY.10`; otherwise `(YY+1).04`). As of November 2026 this is **27.04** (betas are underway), so the target page is `docs/reference/release-notes/27.04-release-notes.md`.
2. Find the shared docs PR: use the GitHub tools to list open PRs in `canonical/landscape-documentation` with labels `changelog` and `automation` (titled `build: draft release notes for Landscape YY.MM`). If one exists, this is THE docs PR — use it regardless of which `YY.MM` page it targets.
3. If a docs PR exists:
   - In the `./landscape-documentation` checkout, check out that PR's head branch (branches were fetched via the wildcard fetch at setup: `git checkout <branch>`). If the branch is not among the fetched refs, skip the docs work for this run — the agent has no credentials to fetch it.
   - Other Landscape bots push to this same shared branch, so the checkout (fetched at setup time) may be stale and another bot may push while you work. The agent environment has NO git credentials — `git fetch` fails here, so NEVER attempt to fetch or rebase. Work from the PR branch ref as fetched at setup; keep every edit strictly inside your own island markers so it applies cleanly over the other bots' island updates. `push_to_pull_request_branch` applies your patch to the branch's live tip in a credentialed job; if a concurrent push made it conflict, the delivery fails safely — do not retry, the next run redoes the work. NEVER force-push over another bot's commits.
   - Update ONLY your own island (see below). If the release-notes page for the in-development version does not exist on that branch, create it from the template below and add it to the toctree in `docs/reference/release-notes/index.md` (newest non-LTS page goes directly under the LTS entries, matching existing ordering).
   - Commit in the docs checkout and deliver via `push_to_pull_request_branch` with `pull_request_number` set to the docs PR number.
4. If no docs PR exists, skip the docs work for this run entirely: make no changes in the `./landscape-documentation` checkout. NEVER create the shared docs PR yourself — it is created weekly by the `release-notes-draft` workflow in `canonical/landscape-documentation`, so if it is missing when you run, that workflow's next scheduled run recreates it and your next run redoes the docs work. (Your own-repo changelog PR logic is unaffected.)
5. If you have no user-facing changes this cycle, leave your island untouched; do not create or update the docs PR. (Your own-repo changelog PR logic is unaffected.)

### Your island

Island markers (HTML comments, invisible in rendered docs). Your slug is `landscape-server-operator`. The full island set, in this fixed order:

1. `landscape-server` — Landscape Server
2. `landscape-client` — Landscape Client
3. `landscape-ui` — Web portal
4. `landscape-go` — Snaps (debarchive, outbox, task-handler services)
5. `landscape-server-operator` — Landscape Server charm
6. `landscape-client-charm` — Landscape Client charm
7. `landscape-debarchive-operator` — Debarchive charm
8. `landscape-task-handler-operator` — Task handler charm

Island format inside `## Additional updates`:

```markdown
<!-- changelog-bot:landscape-server-operator:start -->
### Landscape Server charm

#### Features
- <docs-appropriate bullet>

#### Fixes
- <docs-appropriate bullet>
<!-- changelog-bot:landscape-server-operator:end -->
```

Rules:
- BEFORE writing, read `.github/instructions/release-notes.instructions.md` and `.github/instructions/documentation.instructions.md` in the docs checkout and follow them (applicability: state self-hosted vs SaaS and the component; factual, non-promotional; do not invent benefits, migration steps, or breaking-change claims).
- Rewrite your selected commits into user-facing docs bullets: no conventional-commit prefixes, no `(scope)`, no `(#1234)`, no Jira keys. Keep Launchpad references but format them as `[LP: #NNNN](https://bugs.launchpad.net/landscape/+bug/NNNN)`. Write in the style of existing release notes (see any `docs/reference/release-notes/*.md` page): complete sentences, no trailing period inconsistency, admin-focused.
- Omit `#### Features` / `#### Fixes` when empty. If your island has no entries yet, put `(pending)` as the island body.
- NEVER edit outside your own island markers. Other sections belong to other bots.
- When creating the page, include ALL eight islands in the fixed order above (yours filled, the rest with `(pending)`), so later bot runs find their markers.

### New-page template

File `docs/reference/release-notes/YY.MM-release-notes.md` (dots in the filename, matching `26.10-release-notes.md`; anchor uses dashes):

```markdown
---
myst:
  html_meta:
    description: "Release notes for Landscape YY.MM. Draft; updated automatically until release."
---

(reference-release-notes-YY-MM)=
# YY.MM release notes

> Landscape Server YY.MM runs on Ubuntu 26.04 LTS Resolute Raccoon, 24.04 LTS Noble Numbat, or 22.04 LTS Jammy Jellyfish.

```{note}
This page is a draft maintained automatically until release.
```

## Highlights

(pending - written at release time)

## Additional updates

(eight islands here)

## Upgrade

(pending - written at release time)

## Bug fixes

(pending - written at release time)
```
