import random
from collections.abc import Collection, Iterable, Sequence
from enum import Enum
from fractions import Fraction
from typing import Any, ClassVar, NamedTuple, get_origin, override

from options.base_options import Option
from options.wwrando_options import Options


class MalformedWeightsFile(Exception):
    def __init__(self, *args, weight=None, name: str | None = None, section: str):
        super().__init__(*args)
        self.weight = weight
        self.section = section
        self.name = name

    def __str__(self) -> str:
        msg = super().__str__()
        msg += f". In section {self.section}"
        if self.name:
            msg += f", for entry {self.name}"
        if self.weight is not None:
            msg += f", with given weight {self.weight}"

        return msg + "."


def _parse_percent(value: Any) -> Fraction:
    out: int | Fraction
    if isinstance(value, Fraction):
        out = value
    elif isinstance(value, int):
        out = Fraction(value)
    elif isinstance(value, str):
        if value.endswith("%"):
            out = Fraction(int(value[:-1]), 100)
        elif value.index("/"):
            num, _, den = value.partition("/")
            out = Fraction(int(num), int(den))
        else:
            raise ValueError("Weights must be expressed as fraction or percentage")
    else:
        raise ValueError("Weights must be expressed as fraction or percentage")

    if out > 1:
        raise ValueError("Weights must be <=1")

    return out


class Choice[T](NamedTuple):
    choice: T
    weight: Fraction | int


class OptionWeight:
    name: str
    choices: list[Choice]
    overridable: bool = False

    specialized_weights: ClassVar[dict[str, type["OptionWeight"]]] = {}

    def __init__(self, *, name: str, choices: Sequence[Choice]):
        self.name = name
        self.choices = list(choices)

    @property
    def managed_options(self) -> tuple[Option, ...]:
        return (Options.by_name[self.name],)

    @classmethod
    def from_yaml(cls, yaml_entry, /, section: str) -> "OptionWeight":
        """Loads option weights from a YAML file and sanity-check values and types"""
        for k in cls.specialized_weights:
            if k in yaml_entry:
                return cls.specialized_weights[k].from_yaml(yaml_entry, section=section)

        name = yaml_entry.get("name")
        if not name:
            raise MalformedWeightsFile(f"Entry missing a name: {yaml_entry}", section=section)
        if not name in Options.by_name:
            raise MalformedWeightsFile("Unknown option", name=name, section=section)

        if not set(yaml_entry.keys()) <= {"name", "weight", "choices"}:
            raise MalformedWeightsFile(f"Unknown keys in weights entry", name=name, section=section)

        weight = yaml_entry.get("weight")
        choices = yaml_entry.get("choices")
        if weight is None == choices is None:
            raise MalformedWeightsFile(
                "Exactly one of choices or weight can be set",
                weight=weight,
                name=name,
                section=section,
            )

        if weight is not None:
            try:
                weight = _parse_percent(weight)
                choices = [Choice(True, weight), Choice(False, 1 - weight)]
            except ValueError as e:
                raise MalformedWeightsFile(e, weight=weight, section=section, name=name) from None

        if isinstance(choices, dict):
            choices = choices.items()

        try:
            choices = [Choice(k, _parse_percent(v)) for k, v in choices]
        except ValueError as e:
            raise MalformedWeightsFile(e, weight=weight, section=section, name=name) from None
        if not sum(w for c, w in choices) == 1:
            raise MalformedWeightsFile(
                "Weights don't sum to 1. This is probably unintended",
                section=section,
                name=name,
            )

        cls._check_all_choices_are_valid(Options.by_name[name], choices, section=section)

        return OptionWeight(name=name, choices=choices)

    @classmethod
    def _check_all_choices_are_valid(
        cls,
        option,
        choices: Collection[Choice],
        /,
        section: str = "",
    ):
        check_type = get_origin(option.type) or option.type

        if issubclass(check_type, Enum):
            if any(k not in check_type for k, v in choices):
                bad_key = next(k for k, v in choices if k not in check_type)
                raise MalformedWeightsFile(
                    f"Unknown key for enum-type option: {bad_key}",
                    name=option.name,
                    section=section,
                )
        elif any(not isinstance(k, check_type) for k, v in choices):
            bad_type = next(k for k, v in choices if not isinstance(k, check_type))
            raise MalformedWeightsFile(
                f"Incorrect option type: {type(bad_type)}, expected {check_type}",
                name=option.name,
                section=section,
            )

        if issubclass(check_type, int):
            if option.maximum is not None and any(val > option.maximum for val, _ in choices):
                raise MalformedWeightsFile(
                    f"Maximum for option {option.name} is {option.maximum}, got up to {max(k for k,_v in choices)}",
                    name=option.name,
                    section=section,
                )
            if option.maximum is not None and any(val < option.minimum for val, _ in choices):
                raise MalformedWeightsFile(
                    f"Minimum for option {option.name} is {option.minimum}, got {min(k for k,_v in choices)}",
                    name=option.name,
                    section=section,
                )
        elif issubclass(check_type, bool):
            if set(k for k, _v in choices) != {True, False}:
                raise MalformedWeightsFile(
                    f"Unknown choices for bool option: {choices}",
                    name=option.name,
                    section=section,
                )

    def __init_subclass__(cls, /, characteristic_key, **kwargs):
        super().__init_subclass__(**kwargs)
        OptionWeight.specialized_weights[characteristic_key] = cls

    def roll(self, rng: random.Random) -> dict:
        values, weights = zip(*self.choices)
        return {self.name: rng.choices(values, weights)[0]}


class ChooseSubsetOptionWeight(OptionWeight, characteristic_key="combo"):
    combo: tuple[Option, ...]

    def __init__(
        self,
        *,
        name: str,
        combo: Sequence[Option],
        choices: Sequence[Choice],
    ):
        super().__init__(name=name, choices=choices)
        self.combo = tuple(combo)

    @property
    @override
    def managed_options(self) -> tuple[Option, ...]:
        return self.combo

    @override
    @classmethod
    def from_yaml(cls, yaml_entry, /, section: str) -> "ChooseSubsetOptionWeight":
        combo = yaml_entry.get("combo")
        name = yaml_entry.get("name") or "&".join(combo)

        for opt in combo:
            if opt not in Options.by_name:
                raise MalformedWeightsFile(
                    f"Unknown option: {next(opt for opt in combo if not opt in Options.by_name)}",
                    section=section,
                )
            if Options.by_name[opt].type != bool:
                raise MalformedWeightsFile(
                    "ChooseSubset must take bool-typed options",
                    section=section,
                    name=name,
                )
        combo = tuple(Options.by_name[opt] for opt in combo)

        choices = yaml_entry.get("choices")
        # Choices can be either a mapping, or a list of tuples (items() format), in case keys are unhashable
        # Use !!omap in yaml, or !!python/tuple to use tuples instead of lists for hashability
        if isinstance(choices, dict):
            choices = choices.items()
        choices = [Choice(k, _parse_percent(v)) for k, v in choices]
        cls._check_all_choices_are_valid(combo, choices, section=section, name=name)
        if not sum(w for c, w in choices) == 1:
            raise MalformedWeightsFile(
                "Weights don't sum to 1. This is probably unintended",
                section=section,
                name=name,
                weight=sum(w for _c, w in choices),
            )

        return ChooseSubsetOptionWeight(name=name, combo=combo, choices=choices)

    @override
    @classmethod
    def _check_all_choices_are_valid(
        cls,
        combo,
        choices: Iterable[Choice],
        /,
        section: str = "",
        name: str = "",
    ):
        for chosen_options in choices:
            if not isinstance(chosen_options[0], Sequence):
                raise MalformedWeightsFile("ChooseSubset choices must be sequence of toggles", section=section)
            if any(Options.by_name[opt] not in combo for opt in chosen_options[0]):
                bad_opt = next(opt for opt in chosen_options[0] if Options.by_name[opt] not in combo)
                raise MalformedWeightsFile(
                    f"ChooseSubset choice refers to an option not in combo",
                    name=bad_opt,
                    section=section,
                )

    @override
    def roll(self, rng: random.Random) -> Any:
        chosen = super().roll(rng)[self.name]

        return {rolled_option.name: rolled_option.name in chosen for rolled_option in self.combo}


class DisabledOptionWeight(OptionWeight, characteristic_key="disable"):
    """Disables a previously defined roll.
    This is used for sections overriding previous sections, when combining
    independent settings into a single ChooseSubsetOptionWeight
    """

    managed: bool
    overridable = True

    def __init__(self, *, name: str, managed: bool = False):
        self.managed = managed
        super().__init__(name=name, choices=[])

    @property
    @override
    def managed_options(self) -> tuple[Option, ...]:
        # Since this "unregisters" an option roll, no options are managed
        if self.managed:
            return super().managed_options
        else:
            return ()

    @override
    @classmethod
    def from_yaml(cls, yaml_entry, /, section: str) -> "DisabledOptionWeight":
        name = yaml_entry.get("name")
        if not name:
            raise MalformedWeightsFile(f"Entry missing a name: {yaml_entry}", section=section)
        if not name in Options.by_name:
            raise MalformedWeightsFile("Unknown option", name=name, section=section)

        managed = bool(yaml_entry.get("managed", False))

        return DisabledOptionWeight(name=name, managed=managed)

    @override
    def roll(self, rng: random.Random) -> dict:
        return {}
