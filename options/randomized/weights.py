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


def format_weight(weight: Fraction | int) -> str:
    _, den = weight.as_integer_ratio()
    if weight == 1:
        return "Always"
    elif weight == 0:
        return "Never"
    elif 100 % den == 0:
        return f"{weight:.0%}"
    elif 1000 % den == 0:
        return f"{weight:.1%}"
    elif 1000 % den == 0:
        return f"{weight:.2%}"
    else:
        return str(weight)  # Default format (fraction)


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

    def spoiler_log_line(self) -> str:
        return f"\t{self.name}: {self._spoiler_log_value()}\n"

    def _spoiler_log_value(self) -> str:
        if isinstance(self.choices[0][0], bool):
            for c, w in self.choices:
                if c is True:
                    if w == 1:
                        return "forced on"
                    elif w == 0:
                        return "forced off"
                    else:
                        return format_weight(w)
            assert False  # unreachable if self.choices is well-formed
        else:
            out = ""
            for c, w in self.choices:
                if isinstance(c, (list, tuple)):
                    if c:
                        c = " & ".join(c)
                    else:
                        c = "(none of the options)"
                out += f"\n\t\t{c}: {format_weight(w)}"
            return out


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

    @override
    def spoiler_log_line(self) -> str:
        out = f"\t{self.name}: {', '.join(opt.name for opt in self.combo)}"
        out += super()._spoiler_log_value() + "\n"
        return out


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

    @override
    def spoiler_log_line(self) -> str:
        if self.managed:
            return f"\t{self.name}: (determined by other options)\n"
        else:
            return ""


class CombinationOptionWeight(OptionWeight, characteristic_key="indiv_weights"):

    indiv_weights: list[Choice]
    max_combo: int | None
    min_combo: int

    def __init__(
        self,
        *,
        name: str,
        indiv_weights: Sequence[Choice],
        max_combo: int | None = None,
        min_combo: int = 0,
    ):

        self.indiv_weights = list(indiv_weights)
        self.max_combo = max_combo
        self.min_combo = min_combo
        super().__init__(name=name, choices=self.combination_weights(*indiv_weights))

    def combination_weights(self, *indiv_probs: Choice[Sequence]) -> list[Choice[list]]:
        """Compute aggregate weights for a list of elements where each element can be
        added or removed independently with its own probability
        Optional max_combo limits any combination to have at most that number of elements from indiv_probs
        """

        if any(w > 1 for _, w in indiv_probs):
            raise ValueError("Weights passed to combination_weights include a >1 weight")

        ret: list[Choice[list]] = []
        for combo in range(2 ** len(indiv_probs)):
            # Reject unacceptable options
            if self.max_combo and int.bit_count(combo) > self.max_combo:
                continue
            if int.bit_count(combo) < self.min_combo:
                continue

            items: list[str] = []
            weight = Fraction(1)
            for idx, item in enumerate(indiv_probs):
                if combo & 2**idx:
                    items.extend(item[0])
                    weight *= item[1]
                else:
                    weight *= 1 - item[1]

            if weight > 0:
                ret.append(Choice[list](items, weight))

        if self.max_combo is None and self.min_combo == 0:
            assert sum(w for _, w in ret) == 1
            # XXX: I should check my math, with min_ or max_combo the choices aren't independent anymore
        return ret

    @override
    @classmethod
    def from_yaml(cls, yaml_entry, /, section: str) -> OptionWeight:
        name = yaml_entry.get("name")
        if not name:
            raise MalformedWeightsFile(f"Entry missing a name: {yaml_entry}", section=section)
        if not name in Options.by_name:
            raise MalformedWeightsFile("Unknown option", name=name, section=section)

        indiv_weights = yaml_entry.get("indiv_weights")
        if isinstance(indiv_weights, dict):
            indiv_weights = indiv_weights.items()

        try:
            indiv_weights = [Choice([k] if isinstance(k, str) else k, _parse_percent(v)) for k, v in indiv_weights]
        except ValueError as e:
            raise MalformedWeightsFile(e, section=section, name=name) from None

        return CombinationOptionWeight(
            name=name,
            indiv_weights=indiv_weights,
            min_combo=yaml_entry.get("min_combo", 0),
            max_combo=yaml_entry.get("max_combo"),
        )

    @override
    def _spoiler_log_value(self) -> str:
        if len(self.choices) <= 5:
            # Show combinations individually since there aren't too many
            return super()._spoiler_log_value()

        out = "Choosing a combination of elements "
        if self.min_combo:
            out += f"(minimum {self.min_combo}) "
        elif self.max_combo:
            out += f"(maximum {self.max_combo}) "
        else:
            out += f"(minimum {self.min_combo}, maximum {self.max_combo}) "
        out += "where each has the following probability:"
        for c, w in self.indiv_weights:
            if isinstance(c, (list, tuple)):
                if len(c) > 1:
                    c = " & ".join(c)
                else:
                    c = c[0]
            out += f"\n\t\t{c}: {format_weight(w)}"
        return out
