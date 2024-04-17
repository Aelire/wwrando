import os

from ruamel.yaml import YAML
yaml = YAML(typ="safe")

from wwrando_paths import DATA_PATH

WEIGHTS_PATH = os.path.join(DATA_PATH, "random_settings_weights.yml")


def load_data_files(file=WEIGHTS_PATH):
    with open(file) as f:
        data = yaml.load(f)

    # Ensure all section names can be used as enum fields
    assert all(ident.isidentifier() for ident in data.keys())
    return data


WEIGHT_DATA = load_data_files()
RANDOM_SETTINGS_PRESETS = {ident: entry.get("name", ident) for ident, entry in WEIGHT_DATA.items()}
