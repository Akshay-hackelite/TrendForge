import unittest

from app.services.youtube_api import (
    fit_social_caption,
    publish_platforms,
    sanitize_youtube_tags,
    youtube_upload_body,
)
from app.services.youtube_metadata import reference_thumbnail_prompt


class YouTubeUploadLimitTests(unittest.TestCase):
    def test_sanitize_strips_illegal_characters(self):
        tags = sanitize_youtube_tags(["#Cluster Headache", "a<b>", "ok, still", "  ", "\"quoted\""])
        self.assertEqual(tags[0], "Cluster Headache")
        self.assertNotIn("#", "".join(tags))
        self.assertNotIn("<", "".join(tags))
        self.assertNotIn(">", "".join(tags))
        self.assertNotIn(",", "".join(tags))
        self.assertTrue(all(tag.strip() for tag in tags))

    def test_tag_budget_stays_under_500(self):
        tags = sanitize_youtube_tags(["word " * 30] * 40)
        joined = ",".join(tags)
        self.assertLessEqual(len(joined), 500)
        self.assertGreaterEqual(len(tags), 1)

    def test_upload_body_omits_invalid_tags_and_clamps_text(self):
        body = youtube_upload_body("T" * 180, "D" * 6000, ["#", "<", ""], "chan")
        snippet = body["snippet"]
        self.assertNotIn("tags", snippet)
        self.assertLessEqual(len(snippet["title"]), 100)
        self.assertLessEqual(len(snippet["description"]), 5000)
        self.assertEqual(snippet["categoryId"], "22")
        self.assertEqual(body["status"]["privacyStatus"], "public")

    def test_blank_title_becomes_untitled(self):
        body = youtube_upload_body("   ", "", [], "chan")
        self.assertEqual(body["snippet"]["title"], "Untitled")

    def test_caption_and_platforms(self):
        self.assertLessEqual(len(fit_social_caption("C" * 5000)), 2200)
        self.assertEqual(
            publish_platforms(post_to_youtube=False, post_to_instagram=True, post_to_facebook=False),
            (False, True, False),
        )
        self.assertEqual(
            publish_platforms(post_to_youtube=True, post_to_instagram=True, post_to_facebook=True),
            (True, True, True),
        )

    def test_reference_prompt_is_general_client(self):
        prompt = reference_thumbnail_prompt(
            client_summary={"name": "Ada", "specialty": "Design"},
            topic={"topic_text": "arm pain"},
            headline="Exact Headline",
            sub_banner="First line",
            language="hinglish",
        )
        lowered = prompt.lower()
        self.assertIn("primary visual identity", lowered)
        self.assertIn("style template", lowered)
        self.assertIn("Exact Headline", prompt)
        self.assertNotIn("same face", lowered)
        self.assertNotIn("same person", lowered)
        portrait = reference_thumbnail_prompt(
            client_summary={"name": "Ada", "specialty": "Design"},
            topic={"topic_text": "arm pain"},
            headline="Exact Headline",
            sub_banner="First line",
            language="hinglish",
            portrait=True,
        ).lower()
        self.assertIn("9:16", portrait)
        self.assertIn("70%", portrait)
        self.assertNotIn("same face", portrait)


if __name__ == "__main__":
    unittest.main()
