import unittest
from unittest import mock

import numpy as np

import watch_phone_answer_fast as watcher


class CaptureSourceTests(unittest.TestCase):
    def test_scrcpy_screen_region_selects_window_capture(self):
        source = watcher.parse_screen_region_argument("scrcpy")

        self.assertEqual(source, ("scrcpy", None))

    def test_numeric_screen_region_selects_desktop_region(self):
        source = watcher.parse_screen_region_argument("10,20,300,400")

        self.assertEqual(source, ("desktop", (10, 20, 300, 400)))

    def test_blank_screen_region_selects_adb_capture(self):
        source = watcher.parse_screen_region_argument("")

        self.assertEqual(source, ("adb", None))

    def test_scrcpy_title_match_is_exact(self):
        self.assertTrue(watcher.is_scrcpy_window_title("Android-Remote-WiFi"))
        self.assertFalse(watcher.is_scrcpy_window_title("Codex - Android-Remote-WiFi notes"))

    def test_scrcpy_window_capture_uses_window_frame_not_desktop_region(self):
        expected_frame = object()
        with (
            mock.patch.object(watcher, "find_scrcpy_window_handle", return_value=123, create=True),
            mock.patch.object(watcher, "print_window_client_image", return_value=expected_frame, create=True),
            mock.patch.object(watcher, "find_window_client_rect", side_effect=AssertionError("desktop capture should not be used")),
        ):
            self.assertIs(watcher.capture_scrcpy_window(), expected_frame)

    def test_preprocess_for_ocr_upscales_small_scrcpy_crop(self):
        crop = np.zeros((100, 80, 3), dtype=np.uint8)

        prepared = watcher.preprocess_for_ocr(crop)

        self.assertGreaterEqual(prepared.shape[0], 260)
        self.assertEqual(len(prepared.shape), 2)

    def test_preprocess_for_ocr_keeps_large_crop_size(self):
        crop = np.zeros((400, 300, 3), dtype=np.uint8)

        prepared = watcher.preprocess_for_ocr(crop)

        self.assertEqual(prepared.shape, (400, 300))


if __name__ == "__main__":
    unittest.main()
