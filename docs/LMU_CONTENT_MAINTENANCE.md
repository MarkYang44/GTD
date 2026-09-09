# LMU content maintenance / 内容维护

The website reads local, reviewed content. It does not fetch external pages at startup or automatically endorse changed advice.
网页只读取本地已整理内容，不在启动时抓取网页，也不会自动认可网络上的新建议。

## Source and verification boundaries / 来源与核验边界

- `lmu_guide_data.py`: existing circuit, car and editorial pairing data. `GUIDE_UPDATED` is its original content date, not a new verification date.
- `lmu_practice_data.py`: all 16 circuit and 16 car notes, individually linked to sources read on 2026-09-09. Each has a source observation and a separately labeled editorial practice/reflection exercise. Circuit sources are official descriptions; car sources are Coach Dave Academy's original LMU driving guides. No lap-time testing was performed. Use `NOTE_REVIEWS` for later per-record review overrides; do not bump `CHECKED_ON` globally to imply all notes were rechecked.
- `lmu_content.py`: recommendation review metadata and snapshots. Pairing source links establish background, not endorsement of a specific recommendation. `RECOMMENDATION_REVIEWS` supports overrides keyed by `circuit-slug:car-slug` after exact-version validation.
- `GAME_REFERENCE` points to the official V1.4.1.4 notes checked during this update. This is a reference build, not a claim of latest-version monitoring or tested compatibility. Many driving guides originate in 2025; do not carry forward their numerical setup settings or BoP rankings as current facts.

`checked_on` 表示资料阅读核验日期；不表示来源发布日期、实测日期或游戏兼容认证。当前全部适用版本为未验证。仅在获得对应推荐的版本验证证据后填写 `applicable_version` 和 `evidence_url`，并重新核验日期。不得仅因修改文案或发布快照，就把核验日期更新为今天。

## Update and publish / 修改与发布

1. Read the specific source again. Update the bilingual observations and exercises together, retaining source links and separating source claims from editorial inference. If evidence is insufficient, retain the unverified state.
2. Update the relevant content and review metadata. A game reference change also belongs in the snapshot.
3. Check for unpublished differences:

```sh
venv/bin/python scripts/publish_lmu_content.py --check
```

4. After reviewing actual edits, publish a new, unique content version (example; change the version/date and summaries to match the real update):

```sh
venv/bin/python scripts/publish_lmu_content.py \
  --version 2026.09.09.2 --date 2026-09-09 \
  --summary-zh '简述本次实际改动' \
  --summary-en 'Describe the actual changes in this release'
```

The command refuses reused versions, empty releases, invalid/future/backdated release dates, and unsafe version filenames. It creates a snapshot and appends a release manifest entry; it does not commit or push. Existing snapshots must not be edited after publication. `/kozekilmu/updates` compares adjacent snapshots to show additions, removals and before/after fields. Baseline import was captured on 2026-09-09; it is not reconstructed historical verification.

发布命令不会自动更新来源核验日期，也不会自动提交 Git。页面按快照显示真实差异；修改内容后，快照一致性测试会要求发布新版本。日常维护时请保留旧快照，勿用覆盖旧文件的方式掩盖变化。

5. Validate before committing:

```sh
venv/bin/python -m unittest discover -s tests
venv/bin/python scripts/publish_lmu_content.py --check
```

Run the separate browser suite using the project's documented Playwright environment when changing templates or interaction.
