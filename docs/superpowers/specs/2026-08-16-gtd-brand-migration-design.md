# GTD Brand Migration Design

## Goal

Rename the public project brand to **GTD — Generalized Transmedia Downloader** while preserving downloader behavior, existing CLI invocation, persisted browser preferences, logging compatibility, dependencies, and runtime paths.

## Naming Rules

- README heading and compact UI surfaces use `GTD`.
- README subtitle, browser title, application description, and other explanatory surfaces use `Generalized Transmedia Downloader` or `GTD — Generalized Transmedia Downloader`.
- The GitHub repository target is `MarkYang44/GTD`.
- Clone examples and repository paths use `GTD`.
- The local project root is renamed to `GTD` after Git and worktree operations finish.
- No Python import namespace or CLI command is renamed.

## Files in Scope

- `README.md`: heading, subtitle, naming explanation, directory trees, shell paths, and startup examples.
- `app.py`: module description and Web startup banner.
- `main.py`: CLI module description and interactive input banners.
- `templates/index.html`: browser title only; layout and visual content stay unchanged.
- `templates/guide.html`: browser title and service accessibility label.
- `static/site.webmanifest`: full PWA name and compact `GTD` short name.
- `docs/WEB_GUIDE.md`: current Web guide introduction.
- Historical plans/specifications: safe repository path examples and proposed user-facing extension labels.
- `tests/test_web_progress.py`, `tests/test_web_guide.py`, and `tests/test_cli_audio.py`: public-brand contracts.
- New migration design and plan documents.

No package, Docker, Cargo, deployment, GitHub Actions, environment example, package lock, or package metadata file exists in the repository, so none is added.

## Compatibility-Preserved Identifiers

- Keep `multiple_video_downloader.<path>` as the Python logger namespace. Changing it could break external log filters and it is not user-facing branding.
- Keep `multiple-video-downloader.download-directory-history.v1` as the browser local-storage key. Changing it would discard each browser's saved download-directory history.
- Keep `MVD_ARIA2C_PATH` as an existing public environment variable. Renaming it would break configured aria2c paths; the README continues documenting the compatibility variable.
- Historical test artifact filenames under `/tmp` may be renamed to `gtd-*` because they are neither runtime nor persisted APIs.

## Git and GitHub Flow

1. Implement and verify on the isolated `chore/rename-gtd` branch.
2. Create one commit named `chore: rename project to GTD`.
3. Fast-forward `main` and push normally to the existing `origin`.
4. GitHub CLI is unavailable in the inspected environment, so do not create a replacement repository and do not point `origin` at an unverified target.
5. The user renames the repository to `GTD` in GitHub Settings, then updates `origin` to the new URL and fetches it.
6. Rename the local root directory to `GTD` only after linked worktree cleanup.
7. The ignored local `venv` contains absolute shebang and activation paths. After the move, repair it in place with the same system Python and verify Python, pip, yt-dlp, and the test suite from the new root. This preserves installed packages while avoiding a broken local runtime.

## Validation

- Run focused brand contracts through red and green states.
- Search all tracked text for legacy brand variants and classify any retained occurrences.
- Run all Python unit tests, compileall, JavaScript syntax checks, JSON parsing, and `git diff --check`.
- Start Flask on a temporary loopback port, confirm `/`, `/guide`, `/api/capabilities`, and static manifest responses, then stop only that verified process.
- After the local root move, verify the repaired virtual environment contains no legacy absolute path and rerun the complete test suite from `/Users/markyang/Projects/GTD`.
- Inspect `git status`, diff statistics, full diff, branch, commit, and remote.
- Do not perform a real media download because the migration does not change downloader logic and such a run would create unrelated user files.
