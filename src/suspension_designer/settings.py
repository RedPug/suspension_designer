import os
import json

class SettingsManager:
    _settings = {}
    _default_settings = {
        "last_opened_files": []
    }

    settings_dir = "./user_data/user_settings.json"

    @staticmethod
    def get(key, default=None):
        return SettingsManager._settings.get(key, default)

    @staticmethod
    def set(key, value):
        SettingsManager._settings[key] = value

    @staticmethod
    def read():
        if not os.path.exists(SettingsManager.settings_dir):
            os.makedirs(os.path.dirname(SettingsManager.settings_dir), exist_ok=True)
            with open(SettingsManager.settings_dir, "w") as f:
                json.dump(SettingsManager._default_settings, f)
                print(f"Created default settings file at {SettingsManager.settings_dir}")

        with open(SettingsManager.settings_dir, "r") as f:
            SettingsManager._settings = json.load(f)

    @staticmethod
    def save():
        with open(SettingsManager.settings_dir, "w") as f:
            json.dump(SettingsManager._settings, f)
