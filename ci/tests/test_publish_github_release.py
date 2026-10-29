import copy
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import urllib.parse
import urllib.request

spec = importlib.util.spec_from_file_location(
    "publisher", Path(__file__).resolve().parents[1] / "publish_github_release.py"
)
p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)


def environment():
    return {
        "CI_SERVER_HOST": "git.tak.gov", "CI_PROJECT_PATH": p.PROJECT,
        "CI_COMMIT_BRANCH": "main", "CI_DEFAULT_BRANCH": "main",
        "CI_COMMIT_REF_PROTECTED": "true", "CI_PIPELINE_SOURCE": "push",
        "GOTENNA_GITHUB_TOKEN": "fixture",
        "CI_PROJECT_ID": "6941", "CI_PIPELINE_ID": "123", "CI_PIPELINE_IID": "12",
        "CI_COMMIT_SHA": "a" * 40,
        "CI_PIPELINE_URL": f"https://git.tak.gov/{p.PROJECT}/-/pipelines/123",
    }


def asset(iid, asset_id=1):
    name = f"GoTenna-p{iid}.apk"
    return {"id": asset_id, "name": name, "label": name, "state": "uploaded", "size": 3}


class API:
    def __init__(self, state=None):
        self.repo = {"full_name": p.REPO, "archived": False, "disabled": False}
        self.tag = True
        self.release = None
        if state:
            self.release = {
                "id": 1, "tag_name": p.TAG, "draft": False, "prerelease": False,
                "body": f"<!-- {p.MARKER} {json.dumps(state)} -->",
            }
        self.items, self.calls = [], []
        self.bad_download = False
        self.failure = None

    def request(self, method, path, data=None, **kwargs):
        self.calls.append((method, path))
        if self.failure and self.failure(method, path):
            raise p.PublishError("Injected API failure")
        if method == "GET" and path == "":
            return self.repo
        if path.startswith("git/ref/"):
            return {"ref": p.TAG} if self.tag else None
        if path.startswith("releases/tags/"):
            return copy.deepcopy(self.release)
        if method == "POST" and path == "releases":
            self.release = dict(data, id=1)
            return copy.deepcopy(self.release)
        if method == "POST" and "/assets?" in path:
            item = asset(12, 100)
            self.items.append(item)
            return item
        if method == "PATCH":
            self.release.update(data)
            return copy.deepcopy(self.release)
        if method == "GET" and path == "releases/1":
            return copy.deepcopy(self.release)
        if method == "DELETE":
            self.items = [a for a in self.items if a["id"] != int(path.rsplit("/", 1)[1])]
            return None
        raise AssertionError((method, path))

    def assets(self, release_id):
        return copy.deepcopy(self.items)

    def download_digest(self, asset_id):
        self.calls.append(("DOWNLOAD", str(asset_id)))
        return 3, "bad" if self.bad_download else hashlib.sha256(b"apk").hexdigest()


class PublisherTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.output = self.root / "verified-release"
        self.output.mkdir()
        self.apk = self.output / "weartak-plugin-gotenna-release.apk"
        self.apk.write_bytes(b"apk")
        self.digest = hashlib.sha256(b"apk").hexdigest()
        self.state = p.configuration(environment())
        (self.output / "SHA256SUMS").write_text(f"{self.digest}  {self.apk.name}\n")
        (self.output / "signer-sha256.txt").write_text(p.SIGNER)
        (self.output / "provenance.json").write_text(json.dumps(self.state))
        self.metadata = {
            "applicationId": "com.weartak.plugin.gotenna", "variantName": "release",
            "elements": [{"versionCode": 1, "versionName": "0.1.0", "outputFile": "app-release.apk"}],
        }
        self.write_metadata()
        self.sync = unittest.mock.Mock()

    def write_metadata(self):
        (self.output / "output-metadata.json").write_text(json.dumps(self.metadata))

    def publish(self, api):
        p.publish(api, self.state, *p.artifact(self.root, self.state), self.sync)

    def test_required_configuration(self):
        env = environment()
        for key in env:
            invalid = dict(env)
            del invalid[key]
            with self.subTest(key=key), self.assertRaises(p.PublishError):
                p.configuration(invalid)
        for key, value in (
            ("CI_COMMIT_REF_PROTECTED", "false"), ("CI_PIPELINE_SOURCE", "web"),
            ("CI_SERVER_HOST", "other"), ("CI_PROJECT_PATH", "company/gotenna"),
            ("CI_COMMIT_BRANCH", "feature"), ("CI_DEFAULT_BRANCH", "feature"),
            ("CI_PIPELINE_ID", "NaN"), ("CI_COMMIT_SHA", "short"),
            ("CI_PIPELINE_URL", "https://other.example"), ("CI_DEBUG_TRACE", "true"),
        ):
            with self.subTest(key=key), self.assertRaises(p.PublishError):
                p.configuration(dict(env, **{key: value}))

    def test_success_and_retry_are_idempotent(self):
        api = API()
        self.publish(api)
        self.assertFalse(api.release["draft"])
        self.assertFalse(api.release["prerelease"])
        self.assertEqual(api.release["make_latest"], "false")
        self.assertIn(self.state["source_sha"], api.release["body"])
        self.sync.assert_called_once_with(self.state)
        methods = [c[0] for c in api.calls]
        self.assertLess(methods.index("DOWNLOAD"), methods.index("PATCH"))
        self.publish(api)
        self.assertEqual(len(api.items), 1)

    def test_cleanup_only_older_owned_after_confirmation(self):
        api = API(dict(self.state, pipeline_iid=11))
        api.items = [asset(11, 2), dict(asset(10, 3), label="human"), asset(13, 4)]
        self.publish(api)
        self.assertEqual({a["id"] for a in api.items}, {3, 4, 100})
        self.assertLess(api.calls.index(("GET", "releases/1")),
                        api.calls.index(("DELETE", "releases/assets/2")))

    def test_older_pipeline_does_not_sync_or_write(self):
        api = API(dict(self.state, pipeline_iid=13))
        self.publish(api)
        self.sync.assert_not_called()
        self.assertTrue(all(c[0] == "GET" for c in api.calls))

    def test_conflicting_retry_and_unmanaged_release_fail_before_sync(self):
        for change in (
            {"source_sha": "f" * 40}, {"sha256": "wrong"}, {"project_id": "other"},
        ):
            api = API({**self.state, "sha256": self.digest, **change})
            with self.assertRaises(p.PublishError):
                self.publish(api)
        api = API(self.state)
        api.release["body"] = "human release"
        with self.assertRaises(p.PublishError):
            self.publish(api)
        self.sync.assert_not_called()

    def test_missing_anchor_or_wrong_repository_never_writes(self):
        for change in ({"full_name": "company/repo"}, {"archived": True}, {"disabled": True}):
            api = API()
            api.repo.update(change)
            with self.assertRaises(p.PublishError):
                self.publish(api)
            self.assertTrue(all(c[0] == "GET" for c in api.calls))
        api = API()
        api.tag = False
        with self.assertRaises(p.PublishError):
            self.publish(api)
        self.sync.assert_not_called()

    def test_failures_preserve_previous_assets(self):
        for stage in ("download", "upload", "patch", "confirm", "sync"):
            api = API(dict(self.state, pipeline_iid=11))
            old = asset(11, 2)
            api.items = [old]
            self.sync.reset_mock(side_effect=True)
            if stage == "download":
                api.bad_download = True
            elif stage == "sync":
                self.sync.side_effect = p.PublishError("Diverged")
            else:
                api.failure = lambda method, path, stage=stage: (
                    (stage == "upload" and method == "POST" and "/assets?" in path)
                    or (stage == "patch" and method == "PATCH")
                    or (stage == "confirm" and path == "releases/1" and method == "GET")
                )
            with self.subTest(stage=stage), self.assertRaises(p.PublishError):
                self.publish(api)
            self.assertIn(old, api.items)
            self.assertFalse(any(c[0] == "DELETE" for c in api.calls))

    def test_artifact_tampering_and_provenance(self):
        for filename, value in (
            (self.apk.name, b"tampered"), ("SHA256SUMS", b"wrong"),
            ("signer-sha256.txt", b"debug"), ("provenance.json", b"{}"),
        ):
            file = self.output / filename
            old = file.read_bytes()
            file.write_bytes(value)
            with self.subTest(filename=filename), self.assertRaises(p.PublishError):
                p.artifact(self.root, self.state)
            file.write_bytes(old)
        (self.output / "extra.apk").write_bytes(b"other")
        with self.assertRaises(p.PublishError):
            p.artifact(self.root, self.state)

    def test_debug_metadata_rejected(self):
        self.metadata["variantName"] = "debug"
        self.write_metadata()
        with self.assertRaises(p.PublishError):
            p.artifact(self.root, self.state)

    def test_redirect_strips_authentication_and_rejects_http(self):
        request = urllib.request.Request("https://api.github.com/asset",
                                         headers={"Authorization": "fixture"})
        handler = p.SafeRedirect()
        result = handler.redirect_request(request, None, 302, "", {}, "https://storage.example/a")
        self.assertIsNone(result.get_header("Authorization"))
        with self.assertRaises(p.PublishError):
            handler.redirect_request(request, None, 302, "", {}, "http://storage.example/a")

    def test_api_repository_url_has_no_trailing_slash(self):
        api = p.GitHub("fixture")
        for path in ("", "releases/tags/" + p.TAG):
            with patch.object(api.opener, "open", return_value=io.BytesIO(b'{}')) as call:
                api.request("GET", path)
                expected = "https://api.github.com/repos/" + p.REPO
                if path:
                    expected += "/" + path
                self.assertEqual(call.call_args.args[0].full_url, expected)

    def test_source_sync_only_fast_forwards_and_cleans_helper(self):
        calls = []

        def fake_git(*args, env=None):
            calls.append(args)
            if args[0] == "ls-remote":
                return self.state["source_sha"] + "\trefs/heads/main"
            if args == ("rev-parse", "HEAD"):
                return self.state["source_sha"]
            if args == ("rev-parse", "--is-shallow-repository"):
                return "false"
            if "push" in args:
                self.assertTrue(Path(env["GIT_ASKPASS"]).is_file())
            return ""

        with patch.object(p, "git", side_effect=fake_git):
            p.sync_source(self.state, "fixture")
        self.assertTrue(any(c[0] == "merge-base" for c in calls))
        self.assertFalse(any("--force" in c or "--force-with-lease" in c for c in calls))
        self.assertTrue(any(self.state["source_sha"] + ":refs/heads/main" in c for c in calls))

    def test_diverged_source_never_pushes(self):
        calls = []

        def fake_git(*args, env=None):
            calls.append(args)
            if args[0] == "ls-remote":
                return self.state["source_sha"] + "\trefs/heads/main"
            if args == ("rev-parse", "HEAD"):
                return self.state["source_sha"]
            if args == ("rev-parse", "--is-shallow-repository"):
                return "false"
            if args[0] == "merge-base":
                raise p.PublishError("Diverged")
            return ""

        with patch.object(p, "git", side_effect=fake_git):
            with self.assertRaises(p.PublishError):
                p.sync_source(self.state, "fixture")
        self.assertFalse(any("push" in c for c in calls))

    def test_stale_source_never_pushes(self):
        with patch.object(p, "git", return_value="b" * 40 + "\trefs/heads/main") as git:
            with self.assertRaisesRegex(p.PublishError, "Stale"):
                p.sync_source(self.state, "fixture")
            self.assertEqual(git.call_count, 1)


if __name__ == "__main__":
    unittest.main()
