# goTenna WearTAK plugin

WearTAK plugin foundation for future goTenna radio integration. The app implements the WearTAK
plugin binding contract and reports radio support as unavailable. It does not scan for, pair with,
or send data to radios. Open **Plugins > goTenna** in WearTAK for its hosted status page;
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
or build failures fail the job; no prebuilt AAR fallback is used. Verification
retains only JUnit, test and lint reports for 14 days. Signing files and SDK
binaries are never uploaded. Publisher policy tests run without credentials or network.

### Production signing (Sextant/LACE shared key)

After verification passes, `main_release` runs only on protected default-branch
pushes in the canonical Forge project. It uses the same inherited protected,
masked `weartak-plugins` group variables as Sextant and LACE:
`WEARTAK_RELEASE_KEYSTORE_B64`, `RELEASE_STORE_PASSWORD`, `RELEASE_KEY_ALIAS`
and `RELEASE_KEY_PASSWORD`. Missing inputs fail the job; no new key or debug
fallback is allowed. No variables or credentials are provisioned by this change.

The existing Gradle signing helper is identical to Sextant/LACE. The job decodes
the approved key into restrictive temporary files, maps credentials into its
`WEARTAK_RELEASE_*` environment contract, and removes temporary files on exit
and in `after_script`. Debug tracing is refused. Secrets are not written into
properties values or passed as command-line arguments.

`apksigner` must verify exactly the production signer pinned by Sextant/LACE:

```text
1579b600cd84e619e76a91c2db6b031938c999bc2aad926b9a51ec2b166d348d
```

The job also rejects a debuggable APK. Only after these checks pass does it
retain `verified-release/` for 30 days: signed APK, SHA256SUMS, public signer
fingerprint, Gradle metadata and pipeline/source provenance. This establishes
signing compatibility with the reference production
certificate, not device installation, host version compatibility or radio support.
Unprotected branches, merge requests and tags never run production signing.

### Personal GitHub rolling release

The intended destination is the personal repository
[`aegorsuch/weartak-plugin-gotenna`](https://github.com/aegorsuch/weartak-plugin-gotenna),
not a company repository. `publish_github_main` runs after successful verification
and signing, only for protected canonical `main` pushes. Its resource group
`gotenna-github-main` serializes writers, and the job is not interruptible.
It consumes only `main_release` artifacts, checks APK SHA-256, signer attestation,
application/release metadata and exact source/pipeline provenance before any write.

The publisher requires the fixed anchor tag
`TAK.gov-Forge-CI-CD-Pipeline-Release` already present in the personal mirror.
It never creates or moves tags. Source sync checks that the pipeline SHA remains
canonical `main`, checks personal `main` ancestry and performs only a non-force
fast-forward push. Diverged or stale source fails closed; histories are never
rewritten. Authentication uses a temporary askpass helper referencing the
environment, not embedded credentials or token-bearing URLs.

The stable rolling release is titled **TAK.gov Forge CI/CD Pipeline Release
(<version>-p<IID>)**, with asset `GoTenna-p<IID>.apk`; it does not change GitHub's
Latest selection. Provenance identifies source SHA, pipeline URL, APK digest,
version and signer. New releases stay draft until the uploaded APK is downloaded
and size/hash verified. Existing assets remain until release confirmation; only
older assets owned by this publisher are removed. Newer pipelines cannot be
replaced by older ones. Human releases/assets and conflicting retries are refused.

**Secure setup (operator only; this implementation changes no credentials/settings):**
Reuse an already approved credential only if it is authorized for this exact
personal repository. Provide it as `GOTENNA_GITHUB_TOKEN`, protected, masked,
hidden, expansion disabled, environment scope `*`. A fine-grained PAT needs
Contents read/write and Workflows write for source sync touching `.github/workflows/`,
with only `aegorsuch/weartak-plugin-gotenna` selected. Project-specific
`SEXTANT_GITHUB_TOKEN` and `LACE_GITHUB_TOKEN` are not inherited by GoTenna;
their presence does not establish access to this repository. Do not copy secret
values between projects or widen their access without approval.

Create the fixed anchor only through an approved operator action on an existing,
reviewed commit in the personal mirror. Its source archives describe that fixed
anchor, not necessarily the APK source; release provenance is authoritative.
Missing token/anchor or failed access checks fail publication explicitly. Once
prerequisites exist, retry the latest protected-main publisher (older artifacts
may be stale/expired), without bypassing signing or test gates.

Run focused offline publisher tests:

```powershell
python -m unittest discover -s ci\tests -v
```

The GitHub debug prerelease below is not a production artifact substitute.

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
