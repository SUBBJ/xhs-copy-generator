from pathlib import Path
import importlib.util
import sys
import types
import unittest


streamlit_stub = types.SimpleNamespace(
    cache_data=lambda *args, **kwargs: (lambda func: func),
    session_state={},
)
sys.modules.setdefault("streamlit", streamlit_stub)

APP_PATH = Path(__file__).resolve().parents[1] / "app.py"
SPEC = importlib.util.spec_from_file_location("app_module", APP_PATH)
app = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(app)


def build_model_config():
    return {
        "default_model": "deepseek_chat",
        "models": {
            "deepseek_chat": {
                "name": "DeepSeek",
                "provider": "deepseek",
                "model": "deepseek-chat",
                "api_key": "",
                "enabled": True,
            },
            "deepseek_v3": {
                "name": "DeepSeek V3",
                "provider": "deepseek",
                "model": "deepseek-v3",
                "api_key": "",
                "enabled": True,
            },
            "glm_4_flash": {
                "name": "GLM-4-Flash",
                "provider": "zhipu",
                "model": "glm-4-flash",
                "api_key": "",
                "enabled": True,
            },
            "glm_4_7_flash": {
                "name": "GLM-4.7-Flash",
                "provider": "zhipu",
                "model": "glm-4.7-flash",
                "api_key": "",
                "enabled": True,
            },
            "gpt_4o": {
                "name": "GPT-4o",
                "provider": "openai_compatible",
                "model": "gpt-4o",
                "api_key": "",
                "enabled": True,
            },
            "gpt_4o_mini": {
                "name": "GPT-4o-mini",
                "provider": "openai_compatible",
                "model": "gpt-4o-mini",
                "api_key": "",
                "enabled": True,
            },
        },
    }


class ModelKeyManagementTests(unittest.TestCase):
    def test_provider_key_sync_updates_all_models_in_provider(self):
        model_config = build_model_config()

        updated = app.sync_provider_api_key_in_config(model_config, "gpt_4o", "shared-key")

        self.assertEqual(updated["models"]["gpt_4o"]["api_key"], "shared-key")
        self.assertEqual(updated["models"]["gpt_4o_mini"]["api_key"], "shared-key")
        self.assertEqual(updated["models"]["deepseek_chat"]["api_key"], "")

    def test_resolve_provider_api_key_reads_sibling_model_key(self):
        model_config = build_model_config()
        model_config["models"]["glm_4_flash"]["api_key"] = "zhipu-shared"

        api_key = app.get_provider_api_key_from_config(model_config, "glm_4_7_flash")

        self.assertEqual(api_key, "zhipu-shared")

    def test_build_provider_display_options_groups_models(self):
        model_config = build_model_config()

        options = app.build_provider_display_options(model_config)

        labels = [item["name"] for item in options]
        self.assertIn("OpenAI（GPT-4o / GPT-4o-mini）", labels)
        self.assertIn("DeepSeek（DeepSeek / DeepSeek V3）", labels)
        self.assertIn("质谱（GLM-4-Flash / GLM-4.7-Flash）", labels)

    def test_auto_detect_prefers_zhipu_then_falls_back_to_deepseek(self):
        attempts = []

        def fake_verify(api_key, model_info):
            del api_key
            attempts.append(model_info["model"])
            return model_info["model"] == "deepseek-chat"

        model_key, requires_manual = app.detect_model_by_real_verification(
            api_key="candidate-key",
            model_config=build_model_config(),
            verify_func=fake_verify,
        )

        self.assertEqual(attempts, ["glm-4-flash", "deepseek-chat"])
        self.assertEqual(model_key, "deepseek_chat")
        self.assertFalse(requires_manual)

    def test_auto_detect_requests_manual_selection_when_all_verifications_fail(self):
        model_key, requires_manual = app.detect_model_by_real_verification(
            api_key="candidate-key",
            model_config=build_model_config(),
            verify_func=lambda *_args, **_kwargs: False,
        )

        self.assertIsNone(model_key)
        self.assertTrue(requires_manual)


if __name__ == "__main__":
    unittest.main()
