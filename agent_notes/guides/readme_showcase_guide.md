# Public README and showcase maintenance

Updated: 2026-10-22. Release scope: v0.9.0 (`origin/main` at `73f473aa`).

The public README combines presentation screenshots, a GIF preview, an MP4 recording, and a technical description checked against the released code. Development-branch features must not be described as release behavior.

## Media

`presentation/` is Git-ignored. Copy selected public assets into `docs/media/`; do not link the README to ignored local paths. The media index in `docs/media/README.md` maps published filenames to original sources and records the video conversions.

Keep original generated geometry distinct from the AI-edited material study. Screenshots contain particular floor counts, scores, and timings; they are illustrations rather than benchmark evidence.

## Technical claims

Verify settings, network dimensions, optimizer behavior, and protocol fields against the target release's source. The v0.9.0 default is nine floor environments, with a supported range of 1–16. The standard multi-floor evaluation range remains 4–8.

Do not repeat an old test total, dataset count, convergence claim, or speedup without identifying its revision and evidence. Describe daylight terms as geometric proxies. Use the mandated separate throughput and quality benchmarks for performance reporting.

## Validation and publication

Check all relative links and images, inspect video codec/duration, and run `git diff --check` on the documentation changes. Before publishing, test the target release and inspect a documentation-only diff against its remote tracking branch. Preserve existing development changes. Follow `AGENTS.md`: obtain explicit user consent before `git push`.

## Verification for this update

On 2026-10-22, the committed v0.9.0 source was extracted to `/private/tmp/module-lab-v090-preview` to avoid running the active alpha branch or changing its existing edits. The native ABI 3 library built successfully. The release suite ran 170 tests in 47.514 seconds: OK, skipped=2. Local README links resolved, all seven JPGs and the GIF decoded, and the H.264 MP4 duration was verified as 9.833 seconds. Documentation diff whitespace checks passed. No performance benchmarks were run or claimed.
