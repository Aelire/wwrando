import itertools
from copy import copy
from typing import Any

from options.base_options import Option

from .data import WEIGHT_DATA
from .weights import MalformedWeightsFile, OptionWeight


class WeightSet(list[OptionWeight]):
    @property
    def managed_options(self) -> set[Option]:
        return set(itertools.chain(*(o.managed_options for o in self)))

    def is_managed(self, opt: Option) -> bool:
        return any(opt in o.managed_options for o in self)


def parse_weight_data(raw_data: dict[str, Any] = WEIGHT_DATA) -> dict[str, WeightSet]:
    weights: dict[str, dict[str, OptionWeight]] = {}
    for section, sect_info in raw_data.items():
        weights[section] = {}
        if "inherit" in sect_info:
            for included_section in sect_info["inherit"]:
                if included_section == section:
                    raise MalformedWeightsFile(f"Circular reinclusion of section {section}", section=section)
                for opt in weights[included_section].values():
                    if opt.name in weights[section] and not weights[section][opt.name].overridable:
                        raise MalformedWeightsFile("Redeclaration of an option", name=opt.name, section=section)
                    weights[section][opt.name] = copy(opt)
                    weights[section][opt.name].overridable = True
                continue
        for entry in sect_info.get("weights", []):
            optweight = OptionWeight.from_yaml(entry, section=section)
            if optweight.name in weights[section] and not weights[section][optweight.name].overridable:
                raise MalformedWeightsFile("Redeclaration of an option", name=optweight.name, section=section)
            weights[section][optweight.name] = optweight

    return {sect: WeightSet(namedvals.values()) for sect, namedvals in weights.items()}
