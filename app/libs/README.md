# WearTAK SDK dependency

SDK AARs in this directory are ignored local build inputs, not committed binaries.
No vendor goTenna binaries belong here.

Source: <https://git.tak.gov/weartak-plugins/weartak-plugin-sdk.git>

Validated ACTION + v3-compatible SDK source is published at
[`3f924ee6aaface69d9b10e1981f390ee9502b945`](https://github.com/aegorsuch/weartak-plugin-sdk/commit/3f924ee6aaface69d9b10e1981f390ee9502b945).
It was merged through canonical
[MR 2](https://git.tak.gov/weartak-plugins/weartak-plugin-sdk/-/merge_requests/2).
Local debug/release validation used AARs from source commit
`a4f784338efb1d8eb048591a4a3f57b3f7e8ffa3`; its tree is identical to this merge commit.

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
WEARTAK_SDK_REVISION=3f924ee6aaface69d9b10e1981f390ee9502b945
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
