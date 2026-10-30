# WearTAK SDK dependency

SDK AARs in this directory are ignored local build inputs, not committed binaries.
No vendor goTenna binaries belong here.

Source: <https://git.tak.gov/weartak-plugins/weartak-plugin-sdk.git>

Validated ACTION + v3-compatible SDK source with Artifactory repository settings is published at
[`e2ee52402cf5738e86e43c3f6f1ce1594bd6e5ec`](https://github.com/aegorsuch/weartak-plugin-sdk/commit/e2ee52402cf5738e86e43c3f6f1ce1594bd6e5ec).
It was merged through canonical
[MR 4](https://git.tak.gov/weartak-plugins/weartak-plugin-sdk/-/merge_requests/4).
Its tree `19874cd3b54bb080b037a7392aa1bd15f760daa6` matches tested source
`d6a7dc2afb8e54a6178e91d91e61162e756e2dc6`; SDK pipeline 1821655 passed.

CI defaults to the verified repository/revision below. Optional repository variables
`WEARTAK_SDK_REPOSITORY` (GitHub `owner/repo`
containing the SDK source) and `WEARTAK_SDK_REVISION` (full 40-character published commit
SHA containing the ACTION implementation and host-compatible v3 API) override those defaults.
The default GitHub SDK repository is public; no custom read token is required.
`actions/checkout` uses the ordinary workflow token and disables credential persistence.
Do not configure a branch name or guess a published revision.
Missing configuration reports app validation as skipped for PRs/pushes and explicitly
blocks tag release publication until configured.

Built-in CI defaults (no repository variable setup required for the public mirror):

```text
WEARTAK_SDK_REPOSITORY=aegorsuch/weartak-plugin-sdk
WEARTAK_SDK_REVISION=e2ee52402cf5738e86e43c3f6f1ce1594bd6e5ec
```

Overrides are validated and used consistently by checkout. No remote variables were changed.
For a private SDK mirror, use an authorized read-only fine-grained GitHub token with
Contents: read for that repository in `WEARTAK_SDK_READ_TOKEN`; authorize organization
SSO where required. Never place tokens in repository URLs, source files, or logs.

CI checks out and verifies HEAD equals that exact SDK revision, runs its debug/release unit tests and assemblies,
and copies the resulting AARs here before app verification. There is no sibling-worktree
or binary-download fallback. A clean local build likewise needs both AARs built from
the compatible SDK using JDK 17 and Android SDK 34:

1. In the SDK checkout, run `.\gradlew.bat testDebugUnitTest testReleaseUnitTest assembleDebug assembleRelease`.
2. Copy `build\outputs\aar\weartak-plugin-sdk-debug.aar` and
   `build\outputs\aar\weartak-plugin-sdk-release.aar` to this directory.

`MainUiActionContract.createContent` supplies the agreed `ACTION` card encoding:
`actionId`, `actionLabel`, `enabled`, and `actionArgsJson`. Host and plugin must
use a compatible implementation; only a user tap may dispatch the action.
