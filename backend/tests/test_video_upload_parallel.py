import asyncio
import os
import tempfile
import unittest
from unittest.mock import patch

from fastapi import HTTPException

from app import schemas
from app.routes.tracker import _place_posted_url
from app.services.supabase_storage import STORAGE_TIMEOUT_DETAIL, explain_storage_failure
from app.services.video_publish import (
    _execute_video_upload,
    _facebook_resumable_session,
    facebook_connection_fields,
    facebook_is_on_page,
    facebook_public_url,
)
from app.services.youtube_api import IG_CAPTION_MAX


class _Joined:
    def join(self, timeout=None):
        return None


class _GraphResponse:
    def __init__(self, payload, ok=True, text="ok"):
        self._payload = payload
        self.ok = ok
        self.text = text
        self.status_code = 200 if ok else 400

    def json(self):
        return self._payload


def _body(**overrides):
    data = {
        "client_id": "client-1",
        "topic_id": "topic-1",
        "post_to_youtube": True,
        "post_to_instagram": False,
        "post_to_facebook": False,
        "channels": [
            {
                "channel_id": "ch-1",
                "drive_link": "https://files.example/a.mp4",
                "title": "Hinglish title",
                "description": "Desc",
                "tags": ["#pain"],
                "language": "hinglish",
                "topic_id": "topic-1",
            }
        ],
    }
    data.update(overrides)
    return schemas.VideoUploadRequest(**data)


class VideoUploadParallelTests(unittest.TestCase):
    def _run(self, body, *, downloads, upload=None, facebook=None, instagram=None, copy=None, file_size=None):
        stages = []
        recorded = []

        def record(client_id, topic_id, platform, entry, source=None):
            recorded.append((platform, entry.get("url")))

        def default_upload(**kwargs):
            return f"yt-{kwargs['channel_id']}"

        patches = [
            patch("app.services.video_publish._require_client", return_value="client-1"),
            patch("app.services.video_publish.fetch_channel", return_value={"language": "hinglish"}),
            patch("app.services.video_publish.get_user_google_creds", return_value=object()),
            patch("app.services.video_publish._download_all", return_value=(downloads, {})),
            patch("app.services.video_publish._start_caption", return_value=({"text": "caption"}, _Joined())),
            patch("app.services.video_publish.upload_video_to_youtube", side_effect=upload or default_upload),
            patch("app.services.video_publish._publish_facebook_video", side_effect=facebook or (lambda *a, **k: ("fb1", "https://facebook.com/p/videos/fb1", []))),
            patch("app.services.video_publish._publish_instagram_reel", side_effect=instagram or (lambda *a, **k: ("ig1", "https://instagram.com/reel/abc", []))),
            patch("app.services.video_publish._copy_to_storage", side_effect=copy or (lambda *a, **k: "https://example.supabase.co/storage/v1/object/public/media/a.mp4")),
            patch("app.services.video_publish.append_content_video_posted_url", side_effect=record),
            patch("app.services.video_publish.append_content_video_source_url", return_value=None),
        ]
        patches.append(patch("app.services.video_publish._file_size", return_value=1024 if file_size is None else file_size))
        for item in patches:
            item.start()
        try:
            result = _execute_video_upload(body, "user", emit=stages.append)
        finally:
            for item in reversed(patches):
                item.stop()
        return result, stages, recorded

    def test_youtube_is_saved_before_facebook_and_instagram(self):
        body = _body(post_to_facebook=True, post_to_instagram=True)
        result, stages, recorded = self._run(
            body,
            downloads={"https://files.example/a.mp4": "/tmp/not-a-real-upload.mp4"},
        )
        platforms = [item[0] for item in recorded]
        self.assertLess(platforms.index("youtube"), platforms.index("facebook"))
        self.assertLess(platforms.index("facebook"), platforms.index("instagram"))
        self.assertEqual(result["status"], "success")
        self.assertIn("Downloading video…", stages)
        self.assertTrue(any(line.startswith("Uploading to YouTube (hinglish)") for line in stages))
        self.assertIn("Facebook video posted.", stages)
        self.assertTrue(any(line.startswith("Copying video for Instagram") for line in stages))
        self.assertIn("Instagram reel posted.", stages)

    def test_partial_channel_error_still_posts_facebook(self):
        def upload(**kwargs):
            if kwargs["channel_id"] == "ch-2":
                raise HTTPException(status_code=400, detail="YouTube upload timed out")
            return "yt-1"

        body = _body(
            post_to_facebook=True,
            channels=[
                {
                    "channel_id": "ch-1",
                    "drive_link": "https://files.example/a.mp4",
                    "title": "One",
                    "language": "hinglish",
                    "topic_id": "topic-1",
                },
                {
                    "channel_id": "ch-2",
                    "drive_link": "https://files.example/b.mp4",
                    "title": "Two",
                    "language": "arabic",
                    "topic_id": "topic-1",
                },
            ],
        )
        result, _, recorded = self._run(
            body,
            downloads={
                "https://files.example/a.mp4": "/tmp/a.mp4",
                "https://files.example/b.mp4": "/tmp/b.mp4",
            },
            upload=upload,
        )
        self.assertEqual(result["status"], "partial")
        self.assertTrue(any("arabic" in error.lower() for error in result["errors"]))
        self.assertIn("youtube", [item[0] for item in recorded])
        self.assertIn("facebook", [item[0] for item in recorded])

    def test_oversize_instagram_skips_storage_but_facebook_still_runs(self):
        body = _body(post_to_youtube=False, post_to_instagram=True, post_to_facebook=True, social_video_url="https://files.example/big.mp4", channels=[])
        copy_calls = []

        def copy(*args, **kwargs):
            copy_calls.append(args)
            return "https://should-not-be-used"

        result, stages, recorded = self._run(
            body,
            downloads={"https://files.example/big.mp4": "/tmp/big.mp4"},
            copy=copy,
            file_size=2_000_000_000,
        )
        self.assertEqual(copy_calls, [])
        self.assertTrue(any("1 GB" in error for error in result["errors"]))
        self.assertIn("facebook", [item[0] for item in recorded])
        self.assertNotIn("instagram", [item[0] for item in recorded])
        self.assertTrue(any("Instagram reel was not posted" in line for line in stages))

    def test_storage_timeout_is_not_a_youtube_error(self):
        body = _body(post_to_instagram=True)

        def copy(*args, **kwargs):
            raise TimeoutError("Timeout of 120.0s exceeded")

        result, _, recorded = self._run(
            body,
            downloads={"https://files.example/a.mp4": "/tmp/a.mp4"},
            copy=copy,
            file_size=1000,
        )
        self.assertEqual(result["status"], "partial")
        self.assertIn(STORAGE_TIMEOUT_DETAIL, result["errors"])
        self.assertTrue(all("YouTube" not in error for error in result["errors"]))
        self.assertIn("youtube", [item[0] for item in recorded])
        self.assertEqual(explain_storage_failure(TimeoutError("timed out")), STORAGE_TIMEOUT_DETAIL)

    def test_facebook_resumable_never_sends_file_url(self):
        phases = []
        handle = tempfile.NamedTemporaryFile(delete=False)
        handle.write(b"0123456789")
        handle.close()

        def post(url, data=None, files=None, timeout=None):
            self.assertIn("graph-video.facebook.com", url)
            self.assertNotIn("file_url", data or {})
            phase = (data or {}).get("upload_phase")
            phases.append(phase)
            if phase == "start":
                return _GraphResponse({
                    "upload_session_id": "sess",
                    "video_id": "vid1",
                    "start_offset": "0",
                    "end_offset": str(os.path.getsize(handle.name)),
                })
            if phase == "transfer":
                return _GraphResponse({
                    "start_offset": str(os.path.getsize(handle.name)),
                    "end_offset": str(os.path.getsize(handle.name)),
                })
            return _GraphResponse({"id": "vid1"})

        try:
            with patch("app.services.video_publish.requests.post", side_effect=post):
                video_id = _facebook_resumable_session("page", "token", handle.name, "caption", lambda percent: None)
        finally:
            os.remove(handle.name)
        self.assertEqual(video_id, "vid1")
        self.assertEqual(phases, ["start", "transfer", "finish"])

    def test_facebook_token_fields_and_page_link(self):
        page_id, token = facebook_connection_fields({
            "selected_page_id": "page-9",
            "page_access_token": "page-token",
        })
        self.assertEqual(page_id, "page-9")
        self.assertEqual(token, "page-token")
        with self.assertRaises(HTTPException) as ctx:
            facebook_connection_fields({"page_id": "only-page"})
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("Facebook is not connected", str(ctx.exception.detail))
        self.assertEqual(
            facebook_public_url("123", "page-9", ""),
            "https://www.facebook.com/page-9/videos/123",
        )
        self.assertTrue(facebook_is_on_page({
            "published": True,
            "status": {
                "video_status": "ready",
                "processing_phase": {"status": "complete"},
                "publishing_phase": {"status": "complete"},
            },
        }))

    def test_second_link_appends_instead_of_replacing(self):
        card = {
            "destinations": [
                {"id": "slot-1", "platform": "youtube", "language": "hinglish", "url": ""},
            ]
        }
        _place_posted_url(card, "youtube", "https://www.youtube.com/watch?v=aaa", "hinglish")
        _place_posted_url(card, "youtube", "https://www.youtube.com/watch?v=bbb", "hinglish")
        _place_posted_url(card, "youtube", "https://www.youtube.com/watch?v=aaa", "hinglish")
        urls = [row["url"] for row in card["destinations"]]
        self.assertEqual(urls, [
            "https://www.youtube.com/watch?v=aaa",
            "https://www.youtube.com/watch?v=bbb",
        ])

    def test_caption_over_2200_returns_400(self):
        from app.routes.social import social_post_publish

        body = schemas.SocialPostPublishRequest(
            client_id="client-1",
            post_id="post-1",
            caption="C" * (IG_CAPTION_MAX + 1),
            targets=["instagram"],
        )
        with patch("app.routes.social._require_client", return_value={"id": "client-1"}):
            with self.assertRaises(HTTPException) as ctx:
                asyncio.run(social_post_publish(None, body, {"username": "user"}))
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("2200", str(ctx.exception.detail))


if __name__ == "__main__":
    unittest.main()
