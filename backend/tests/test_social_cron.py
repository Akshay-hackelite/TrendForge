import unittest
from datetime import datetime

from app.routes.social import _public_social_image_url, _queue_should_publish

HOST = "https://trendforge.onrender.com"
GCS = "https://storage.googleapis.com/trendforge-bucket/festive.png"
SUPABASE = "https://example.supabase.co/storage/v1/object/public/social/festive.png"


def _old_glue(image_url: str, host: str) -> str:
    """The check that treated the 'api' inside googleapis as an already-prefixed path."""
    if "api" not in image_url:
        return f"{host}/api{image_url}"
    return f"{host}{image_url}"


class PublicSocialImageUrlTests(unittest.TestCase):
    def test_gcs_url_is_unchanged(self):
        self.assertEqual(_public_social_image_url(GCS, HOST), GCS)

    def test_supabase_url_is_unchanged(self):
        self.assertEqual(_public_social_image_url(SUPABASE, HOST), SUPABASE)

    def test_old_render_gcs_glue_is_not_rebuilt(self):
        glued = _old_glue(GCS, HOST)
        self.assertEqual(glued, f"{HOST}{GCS}")
        self.assertNotEqual(_public_social_image_url(GCS, HOST), glued)
        supabase_glued = _old_glue(SUPABASE, HOST)
        self.assertTrue(supabase_glued.startswith(f"{HOST}/apihttps://"))
        self.assertNotEqual(_public_social_image_url(SUPABASE, HOST), supabase_glued)

    def test_local_asset_gets_api_prefix(self):
        self.assertEqual(
            _public_social_image_url("/social.asset/festive.png", HOST),
            f"{HOST}/api/social.asset/festive.png",
        )


class QueueShouldPublishTests(unittest.TestCase):
    def setUp(self):
        self.monday = datetime(2026, 10, 19)
        self.tuesday = datetime(2026, 10, 20)

    def test_frequency_off_or_empty_skips_the_queue(self):
        self.assertFalse(_queue_should_publish({"frequency": "off"}, self.monday))
        self.assertFalse(_queue_should_publish({"frequency": ""}, self.monday))
        self.assertFalse(_queue_should_publish({}, self.monday))
        self.assertFalse(_queue_should_publish(None, self.monday))

    def test_daily_publishes_every_day(self):
        self.assertTrue(_queue_should_publish({"frequency": "daily"}, self.monday))
        self.assertTrue(_queue_should_publish({"frequency": "daily"}, self.tuesday))

    def test_once_a_week_matches_the_selected_day_only(self):
        schedule = {"frequency": "once_a_week", "selected_days": ["Monday"]}
        self.assertTrue(_queue_should_publish(schedule, self.monday))
        self.assertFalse(_queue_should_publish(schedule, self.tuesday))

    def test_weekdays_skip_the_weekend(self):
        saturday = datetime(2026, 10, 24)
        self.assertTrue(_queue_should_publish({"frequency": "weekdays"}, self.monday))
        self.assertFalse(_queue_should_publish({"frequency": "weekdays"}, saturday))


if __name__ == "__main__":
    unittest.main()
