"""Publish verified protected-main APKs to the approved personal mirror only."""

import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request

REPO = "aegorsuch/weartak-plugin-gotenna"
PROJECT = "weartak-plugins/weartak-plugin-gotenna"
TAG = "TAK.gov-Forge-CI-CD-Pipeline-Release"
TITLE = "TAK.gov Forge CI/CD Pipeline Release"
MARKER = "gotenna-rolling-v1"
SIGNER = "1579b600cd84e619e76a91c2db6b031938c999bc2aad926b9a51ec2b166d348d"
ASSET = re.compile(r"GoTenna-p([1-9][0-9]*)\.apk")


class PublishError(Exception):
    pass


class SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if urllib.parse.urlsplit(newurl).scheme != "https":
            raise PublishError("Refusing non-HTTPS redirect.")
        redirect = super().redirect_request(req, fp, code, msg, headers, newurl)
        if redirect is not None:
            redirect.remove_header("Authorization")
        return redirect


class GitHub:
    def __init__(self, token):
        self.token = token
        self.opener = urllib.request.build_opener(SafeRedirect())

    def request(self, method, path, data=None, *, binary=False, missing_ok=False):
        host = "https://uploads.github.com" if binary else "https://api.github.com"
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "GoTenna-Forge-release",
        }
        if data is not None:
            headers["Content-Type"] = (
                "application/vnd.android.package-archive" if binary else "application/json"
            )
            if not binary:
                data = json.dumps(data).encode()
        req = urllib.request.Request(
            f"{host}/repos/{REPO}" + (f"/{path}" if path else ""),
            data=data, headers=headers, method=method,
        )
        try:
            with self.opener.open(req, timeout=120) as response:
                raw = response.read()
                return json.loads(raw) if raw else None
        except urllib.error.HTTPError as error:
            if missing_ok and method == "GET" and error.code == 404:
                return None
            raise PublishError(f"GitHub {method} failed: HTTP {error.code}.") from None
        except urllib.error.URLError:
            raise PublishError("GitHub HTTPS request failed; check runner connectivity.") from None

    def download_digest(self, asset_id):
        req = urllib.request.Request(
            f"https://api.github.com/repos/{REPO}/releases/assets/{asset_id}",
            headers={"Authorization": f"Bearer {self.token}", "Accept": "application/octet-stream"},
        )
        try:
            with self.opener.open(req, timeout=120) as response:
                digest, size = hashlib.sha256(), 0
                while chunk := response.read(1024 * 1024):
                    digest.update(chunk)
                    size += len(chunk)
                return size, digest.hexdigest()
        except (urllib.error.URLError, OSError):
            raise PublishError("Uploaded APK download verification failed.") from None

    def assets(self, release_id):
        items, page = [], 1
        while True:
            batch = self.request("GET", f"releases/{release_id}/assets?per_page=100&page={page}")
            items.extend(batch)
            if len(batch) < 100:
                return items
            page += 1


def configuration(env):
    gates = {
        "CI_SERVER_HOST": "git.tak.gov", "CI_PROJECT_PATH": PROJECT,
        "CI_COMMIT_BRANCH": "main", "CI_DEFAULT_BRANCH": "main",
        "CI_COMMIT_REF_PROTECTED": "true", "CI_PIPELINE_SOURCE": "push",
    }
    for key, value in gates.items():
        if env.get(key) != value:
            raise PublishError(f"Publishing requires {key}={value}.")
    if env.get("CI_DEBUG_TRACE", "false") != "false":
        raise PublishError("Publishing refuses debug tracing.")
    if not env.get("GOTENNA_GITHUB_TOKEN"):
        raise PublishError(
            "Missing GOTENNA_GITHUB_TOKEN: approved protected/masked credential with "
            "Contents: write only for aegorsuch/weartak-plugin-gotenna is required."
        )
    for key in ("CI_PROJECT_ID", "CI_PIPELINE_ID", "CI_PIPELINE_IID"):
        if not re.fullmatch(r"[1-9][0-9]*", env.get(key, "")):
            raise PublishError(f"Invalid {key}.")
    if not re.fullmatch(r"[0-9a-f]{40}", env.get("CI_COMMIT_SHA", "")):
        raise PublishError("Invalid source SHA.")
    url = f"https://git.tak.gov/{PROJECT}/-/pipelines/{env['CI_PIPELINE_ID']}"
    if env.get("CI_PIPELINE_URL") != url:
        raise PublishError("Noncanonical pipeline URL.")
    return {
        "project_id": env["CI_PROJECT_ID"], "pipeline_id": env["CI_PIPELINE_ID"],
        "pipeline_iid": int(env["CI_PIPELINE_IID"]), "source_sha": env["CI_COMMIT_SHA"],
        "pipeline_url": url,
    }


def artifact(root, state):
    output = root / "verified-release"
    apk = output / "weartak-plugin-gotenna-release.apk"
    if list(output.glob("*.apk")) != [apk] or apk.is_symlink() or not apk.is_file():
        raise PublishError("Expected exactly one verified production APK.")
    digest = hashlib.sha256(apk.read_bytes()).hexdigest()
    if (output / "SHA256SUMS").read_text().strip() != f"{digest}  {apk.name}":
        raise PublishError("Production APK checksum mismatch.")
    if (output / "signer-sha256.txt").read_text().strip() != SIGNER:
        raise PublishError("Wrong production signer attestation.")
    provenance = json.loads((output / "provenance.json").read_text())
    if provenance != state:
        raise PublishError("Artifact belongs to another source/pipeline.")
    metadata = json.loads((output / "output-metadata.json").read_text())
    elements = metadata.get("elements", [])
    if (metadata.get("applicationId") != "com.weartak.plugin.gotenna"
            or metadata.get("variantName") != "release" or len(elements) != 1
            or elements[0].get("outputFile") != "app-release.apk"):
        raise PublishError("Unexpected Gradle release metadata.")
    version, code = elements[0].get("versionName"), elements[0].get("versionCode")
    if (not isinstance(version, str) or not re.fullmatch(r"[0-9A-Za-z.+_-]+", version)
            or type(code) is not int or code <= 0):
        raise PublishError("Invalid APK version.")
    return apk, digest, version, code


def release_state(release, project_id):
    matches = re.findall(rf"<!-- {MARKER} (.*?) -->", release.get("body") or "")
    if len(matches) != 1:
        raise PublishError("Release is not automation-owned.")
    previous = json.loads(matches[0])
    if (not isinstance(previous, dict) or previous.get("project_id") != project_id
            or type(previous.get("pipeline_iid")) is not int or previous["pipeline_iid"] <= 0
            or release.get("tag_name") != TAG or release.get("prerelease")):
        raise PublishError("Invalid release ownership/classification.")
    return previous


def git(*args, env=None):
    result = subprocess.run(
        ["git", *args], env=env, capture_output=True, text=True, check=False
    )
    if result.returncode:
        raise PublishError("Non-force source synchronization failed; inspect branch ancestry/access.")
    return result.stdout.strip()


def sync_source(state, token):
    # Never rewrite personal history or create/move release tags.
    source = "origin"
    target = f"https://github.com/{REPO}.git"
    latest = git("ls-remote", source, "refs/heads/main").split()
    if not latest or latest[0] != state["source_sha"]:
        raise PublishError("Stale pipeline: canonical main has advanced.")
    if git("rev-parse", "HEAD") != state["source_sha"]:
        raise PublishError("Checkout does not match artifact source.")
    if git("rev-parse", "--is-shallow-repository") == "true":
        git("fetch", "--unshallow", source, "main")
    with tempfile.TemporaryDirectory(prefix="gotenna-askpass-") as directory:
        helper = Path(directory) / "askpass.sh"
        helper.write_text(
            '#!/bin/sh\ncase "$1" in *Username*) printf "%s\\n" x-access-token;; '
            '*) printf "%s\\n" "$GOTENNA_GITHUB_TOKEN";; esac\n'
        )
        helper.chmod(0o700)
        env = dict(os.environ, GIT_ASKPASS=str(helper), GIT_TERMINAL_PROMPT="0",
                   GOTENNA_GITHUB_TOKEN=token)
        git("-c", "credential.helper=", "fetch", target, "refs/heads/main", env=env)
        git("merge-base", "--is-ancestor", "FETCH_HEAD", state["source_sha"], env=env)
        git("-c", "credential.helper=", "push", target,
            f"{state['source_sha']}:refs/heads/main", env=env)


def asset_pipeline(asset):
    match = ASSET.fullmatch(asset.get("name", ""))
    if match and asset.get("label") == asset["name"]:
        return int(match[1])
    return None


def publish(api, state, apk, digest, version, code, sync):
    repository = api.request("GET", "")
    if (repository.get("full_name") != REPO or repository.get("archived") is not False
            or repository.get("disabled") is not False):
        raise PublishError("Destination is not the approved active personal repository.")
    if not api.request("GET", f"git/ref/tags/{TAG}", missing_ok=True):
        raise PublishError(f"Missing approved fixed anchor tag {TAG}; no tag will be created.")
    release = api.request("GET", f"releases/tags/{TAG}", missing_ok=True)
    if release:
        previous = release_state(release, state["project_id"])
        if previous["pipeline_iid"] > state["pipeline_iid"]:
            print("Skipping older pipeline; newer release retained.")
            return
        if (previous["pipeline_iid"] == state["pipeline_iid"]
                and (previous.get("source_sha") != state["source_sha"]
                     or previous.get("sha256") != digest)):
            raise PublishError("Conflicting retry source/artifact.")
    sync(state)
    state = dict(state, sha256=digest)
    title = f"{TITLE} ({version}-p{state['pipeline_iid']})"
    body = (
        "Production-signed GoTenna WearTAK plugin. Radio transport remains unavailable.\n\n"
        f"Version: {version} (versionCode {code})\n\n"
        f"Pipeline: {state['pipeline_url']}\n\nSource: `{state['source_sha']}`\n\n"
        f"APK SHA-256: `{digest}`\n\nSigner SHA-256: `{SIGNER}`\n\n"
        "Install the APK asset, not the fixed-anchor source archives. "
        "Device/host compatibility has not been tested by this pipeline.\n\n"
        f"<!-- {MARKER} {json.dumps(state, sort_keys=True)} -->"
    )
    if not release:
        release = api.request("POST", "releases", {
            "tag_name": TAG, "name": title, "body": body, "draft": True,
            "prerelease": False, "make_latest": "false",
        })
    release_id = release["id"]
    assets = api.assets(release_id)
    name = f"GoTenna-p{state['pipeline_iid']}.apk"
    existing = [item for item in assets if item["name"] == name]
    if len(existing) > 1 or (existing and asset_pipeline(existing[0]) is None):
        raise PublishError("Unmanaged/ambiguous asset collision.")
    if existing:
        uploaded = existing[0]
    else:
        query = urllib.parse.urlencode({"name": name, "label": name})
        uploaded = api.request(
            "POST", f"releases/{release_id}/assets?{query}", apk.read_bytes(), binary=True
        )
    size = apk.stat().st_size
    if (uploaded.get("state") != "uploaded" or uploaded.get("size") != size
            or api.download_digest(uploaded["id"]) != (size, digest)):
        raise PublishError("Uploaded APK verification failed; previous assets retained.")
    api.request("PATCH", f"releases/{release_id}", {
        "name": title, "body": body, "draft": False,
        "prerelease": False, "make_latest": "false",
    })
    confirmed = api.request("GET", f"releases/{release_id}")
    if (confirmed.get("draft") or confirmed.get("name") != title
            or release_state(confirmed, state["project_id"]) != state
            or not any(a["id"] == uploaded["id"] and a.get("state") == "uploaded"
                       and a.get("size") == size for a in api.assets(release_id))):
        raise PublishError("Release confirmation failed; previous assets retained.")
    for old in assets:
        owner = asset_pipeline(old)
        if owner is not None and owner < state["pipeline_iid"]:
            api.request("DELETE", f"releases/assets/{old['id']}")
    print(f"Published {REPO}: {TAG}, source {state['source_sha']}, SHA256 {digest}")


def main():
    try:
        state = configuration(os.environ)
        apk, digest, version, code = artifact(Path.cwd(), state)
        token = os.environ["GOTENNA_GITHUB_TOKEN"]
        publish(GitHub(token), state, apk, digest, version, code,
                lambda value: sync_source(value, token))
    except (PublishError, OSError, ValueError, KeyError, TypeError) as error:
        message = str(error) if isinstance(error, PublishError) else type(error).__name__
        print(f"ERROR: {message} Publication incomplete; see README.md.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
