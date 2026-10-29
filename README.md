# goTenna WearTAK plugin

WearTAK plugin foundation for future goTenna radio integration. The app implements the WearTAK
plugin binding contract and reports radio support as unavailable. It does not scan for, pair with,
or send data to radios. Open **Plugins > GoTenna** in WearTAK for its hosted status page;
the plugin does not expose a separate launcher activity.

## Hosted WearTAK UI

The service advertises `hostedMainUi = true` and `externalMainActivity = false`.
`getMainUiSchema()` provides a `STATUS` card explaining the unavailable transport
and an SDK `ACTION` card labeled **Refresh status**.
`gotenna.refresh` is a local-only action through `invokeMainUiAction()` that notifies
the host to reload UI state and plugin status; it never scans for or connects to a radio.
Unknown actions report a plugin error. Refresh after shutdown is rejected.
V3 host initialization delegates to the same lifecycle path; no PCM subscription
or additional radio capability is enabled.

Interactive cards use `MainUiActionContract.createContent` from the shared WearTAK SDK;
no custom state bindings or unsupported radio controls are advertised. STATUS
title/subtitle contain the complete explanation; the host need not interpret opaque
state Bundle keys. The action is dispatched only on an explicit user tap.
Host discovery, signature-compatible installation, and hosted-card rendering must be
available in WearTAK to display the page, including support for the shared `ACTION`
contract. SDK source configuration and local validation provenance are documented in
[`app/libs/README.md`](app/libs/README.md).

## What APK inspection established

Local, read-only inspection of goTenna-supplied ATAK plugin 2.4.0 (`com.gotenna.atak`) established:

- Plugin targets ATAK 5.7.0 CIV and registers `com.gotenna.atak.plugin.GoTennaLifecycle`.
- Manifest requests Bluetooth permissions, among other ATAK app permissions.
- DEX metadata includes GoTenna ATAK components, radio-manager and IPC-related classes.
- APK also contains SQLiteCipher and versioned GoTenna database assets.

These are observations about the ATAK plugin, not a documented WearTAK transport contract. Inspection
did not establish a supported GoTenna Wear OS SDK or radio protocol. This app therefore does not
guess at Bluetooth services, commands, pairing, encryption, or message formats. Obtain a vendor
SDK/API or protocol specification before implementing transport behavior.

The APK and its decompiled contents are not part of this repository.

## Build and test

Requires JDK 17, Android SDK, and compatible SDK AARs built as described in
[`app/libs/README.md`](app/libs/README.md). AARs are ignored, not committed:

```powershell
.\gradlew.bat :app:testDebugUnitTest :app:assembleDebug
```

WearTAK SDK AAR dependencies must include the shared ACTION contract. No signing key or signing
credentials are included; release signing may be configured externally using the existing
`WEARTAK_SIGNING_PROPERTIES` convention.

## TAK.gov Forge CI

Canonical source is `weartak-plugins/weartak-plugin-gotenna` on TAK.gov Forge,
default branch `main`. `.gitlab-ci.yml` verifies merge requests, branch pushes,
tags and manual branch/tag pipelines. Push pipelines are suppressed when an open
merge request already provides coverage. A Linux Docker/Kubernetes runner must
be able to pull the digest-pinned Android 34 image and reach GitHub, Google's
Android/Maven repositories, Maven Central and Gradle distribution services.
The image supplies JDK 21 (supported by Gradle 8.10.2), Android SDK 34 and
build-tools 34.0.0. Java/Kotlin bytecode still targets Java 17.

Forge builds the same public, commit-pinned SDK as GitHub CI, verifies its checkout,
runs SDK debug/release unit tests and assemblies, then stages both SDK AARs.
It runs plugin debug/release unit tests, assemblies and lint. Dependency checkout
or build failures fail the job; no prebuilt AAR fallback is used. Only JUnit,
test and lint reports are retained for 14 days. **No APKs, signing files or SDK
binaries are uploaded, and no release is published**, including on tag pipelines.

### Production rolling release blocked

The intended destination is the personal repository
[`aegorsuch/weartak-plugin-gotenna`](https://github.com/aegorsuch/weartak-plugin-gotenna),
not a company repository. No Forge publisher is enabled: existing release signing
is optional and this checkout contains no production signing material or Forge
signing setup. Without it, `assembleRelease` produces an unsigned APK, not a
distributable production release. The GitHub debug prerelease described below
is not a substitute.

Before adding the protected-tag, fixed-tag rolling-release publisher, an operator
must provision the existing signing contract on a protected runner:
`WEARTAK_SIGNING_PROPERTIES` must reference a signing properties file (or an
ignored root `signing.properties` must exist). It must provide
`RELEASE_KEYSTORE_FILE`, `RELEASE_STORE_PASSWORD`, `RELEASE_KEY_ALIAS` and
`RELEASE_KEY_PASSWORD`; corresponding `WEARTAK_RELEASE_*` environment values can
override them, but the properties file must still exist. The keystore must use
the production WearTAK host certificate because binding requires matching
signatures. Neither credentials nor GitLab variables are created by this change.

Publication also needs a trusted expected production certificate SHA-256 digest,
protected source-tag policy and an authorized token scoped only to the personal
destination. A future publisher must require successful verification, validate
the APK signature and certificate against that trusted digest, reject debug or
unsigned APKs, and serialize updates to the fixed rolling-release tag/assets.
Until these prerequisites exist, Forge remains verification-only with no
GitHub write access.

## GitHub CI and releases

`.github/workflows/ci.yml` runs unit tests, debug assembly and Android lint for pushes,
pull requests and manual runs. Pushing a `v*` tag publishes the verified debug APK and
SHA-256 checksum as a GitHub **prerelease**, only after those checks pass.
No vendor APK or analysis artifact is published.

**SDK source pin:** CI defaults to the published repository/revision below.
Override with repository variables `WEARTAK_SDK_REPOSITORY`
(GitHub `owner/repo`) and `WEARTAK_SDK_REVISION` (full published commit SHA
including ACTION and v3 support). The default SDK source is public; no custom token
or private-repository access is required. Checkout uses the ordinary workflow token
without persisting credentials, and verifies HEAD against the pin. Only private
repository overrides need authorized read-only `WEARTAK_SDK_READ_TOKEN`; fork pull
requests do not receive that optional secret. CI builds/tests the pinned SDK before the app.
Missing configuration produces an actionable PR/push notice and skips app validation;
it never counts as a successful app build. Tag publication explicitly fails until the
SDK is published/configured and app checks pass. No local binary fallback is used.
The host-compatible ACTION SDK is now published; use these verified values:

```text
WEARTAK_SDK_REPOSITORY=aegorsuch/weartak-plugin-sdk
WEARTAK_SDK_REVISION=3f924ee6aaface69d9b10e1981f390ee9502b945
```

See the [published SDK merge commit](https://github.com/aegorsuch/weartak-plugin-sdk/commit/3f924ee6aaface69d9b10e1981f390ee9502b945).
Remote repository variables have not been set by this implementation.

The attached APK is explicitly development-only, signed with a CI-generated Android debug
key, not a production certificate. WearTAK's signature binding permission requires matching
host/plugin certificates. CI debug keys are ephemeral and will not match a normal installed
host or prior CI build. Production releases require externally supplied matching WearTAK
signing credentials and a separate production-signing release configuration; this automation
does not pretend to provide either.

The reusable `release-testing.yml` workflow creates an idempotent release-testing issue after
publication, or can be run manually with a published tag. Set repository variable
`RELEASE_TESTER` to an eligible GitHub username to assign it. Actions must have permission to
create issues and releases, and Issues must be enabled. Tag pushes and remote workflow execution
have not been performed as part of local implementation.
