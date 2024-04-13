import os

from ruamel.yaml import YAML
yaml = YAML(typ="safe")

from wwrando_paths import DATA_PATH

WEIGHTS_PATH = os.path.join(DATA_PATH, "random_settings_weights.yml")


def load_data_files(file=WEIGHTS_PATH):
    with open(file) as f:
        data = yaml.load(f)

    assert all(isinstance(k, str) for k in data.keys())
    return data


WEIGHT_DATA = load_data_files()
RANDOM_SETTINGS_PRESETS = list(WEIGHT_DATA.keys())
