from typing import override

from logic.logic import Logic, TooFewProgressionLocationsError
from options.randomized.weight_sets import WeightSet, parse_weight_data
from options.wwrando_options import Options, RandomSettingsPreset
from randomizers.base_randomizer import BaseRandomizer


class SettingsRandomizer(BaseRandomizer):
    _weights: dict[RandomSettingsPreset, WeightSet] | None = None

    @override
    def is_enabled(self) -> bool:
        return self.options.randomize_settings

    @override
    def _randomize(self):
        for _ in range(10):
            self.select_settings()
            self.rando.starting_items = self.rando.build_starting_items_from_options()
            try:
                self.check_for_valid_seed()
                break
            except TooFewProgressionLocationsError:
                # Rerolling will use the already-advanced state of the rng and thus give us a new set of settings
                continue

    @classmethod
    def weights(cls, section: RandomSettingsPreset) -> WeightSet:
        if not cls._weights:
            cls._weights = parse_weight_data()
        return cls._weights[section]

    @classmethod
    def normalize_options(cls, options: Options):
        if options.randomize_settings:
            all_default_values = Options()
            for option in options.all:
                if cls.weights(options.random_settings_preset).is_managed(option):
                    options[option.name] = all_default_values[option.name]

    def select_settings(self) -> None:
        assert self.rng
        for weight_info in self.weights(self.options.random_settings_preset):
            for set_opt, set_val in weight_info.roll(self.rng).items():
                self.options[set_opt] = set_val

    @override
    def _save(self):
        # This randomizer only modifies behavior of other randomizers, and doesn't change the seed by itself
        pass

    @property
    def progress_randomize_duration_weight(self) -> int:
        return 1

    @property
    def progress_save_duration_weight(self) -> int:
        return 0

    @property
    def progress_randomize_text(self) -> str:
        return "Randomizing settings..."

    @property
    def progress_save_text(self) -> str:
        return ""

    def write_to_non_spoiler_log(self) -> str:
        out = f"Random Settings Preset: {self.options.random_settings_preset}\n\n"
        out += "Settings probabilities:\n"
        for w in self.weights(self.options.random_settings_preset):
            out += w.spoiler_log_line()
        out += "\n"
        return out

    def write_to_spoiler_log(self) -> str:
        out = f"Random Settings Preset: {self.options.random_settings_preset}\n"
        out += "Randomized settings: "
        opts = []
        for w in self.weights(self.options.random_settings_preset):
            for o in w.managed_options:
                if o.name == "randomized_gear":
                    continue
                opts.append(f"{o.name}: {getattr(self.options, o.name)}")
        out += ", ".join(opts)
        out += "\n\n"
        return out

    def check_for_valid_seed(self):
        logic_for_progression_items = Logic(self.rando)
        logic_for_progression_items.initialize_from_randomizer_state()
        logic_for_progression_items.check_enough_progression_locations()
