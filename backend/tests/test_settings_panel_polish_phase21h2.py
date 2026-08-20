from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
SETTINGS = ROOT / "src" / "app" / "panels" / "SettingsOverlay.tsx"
SETTINGS_CSS = ROOT / "src" / "app" / "panels" / "SettingsOverlay.css"


class SettingsPanelPolishPhase21H2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = SETTINGS.read_text(encoding="utf-8")
        cls.css = SETTINGS_CSS.read_text(encoding="utf-8")

    def test_settings_panel_uses_real_voice_preferences_without_new_app_state(self):
        self.assertIn('value={speechRate}', self.source)
        self.assertIn('min="0.75"', self.source)
        self.assertIn('max="1.35"', self.source)
        self.assertIn('adjustSpeechRate(Number(event.target.value))', self.source)
        self.assertIn('setVoiceOutput(nextEnabled)', self.source)
        self.assertIn('disabled={!voiceOutputEnabled}', self.source)

    def test_settings_panel_surfaces_backend_status_provider_and_model(self):
        self.assertIn("backendStatus?.provider || 'Unknown'", self.source)
        self.assertIn("backendStatus?.model || 'Unknown'", self.source)
        self.assertIn("backendStatus.ok", self.source)
        self.assertIn('settings-health-chip', self.source)

    def test_settings_styles_are_scoped_and_tablet_compact(self):
        self.assertIn('.settings-panel', self.css)
        self.assertIn('.settings-rate-slider', self.css)
        self.assertIn('.settings-grid', self.css)
        self.assertIn('@media (max-height: 660px)', self.css)
        self.assertIn('@media (max-width: 900px)', self.css)


if __name__ == '__main__':
    unittest.main()
