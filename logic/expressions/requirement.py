import abc
from collections.abc import Iterable
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Any, Self, TypeVar, override

from logic.logic import Logic
from options.wwrando_options import Options
if TYPE_CHECKING:
  from logic.logic import Logic

type StaticReq = ItemReq|NothingReq|ImpossibleReq|BooleanCombinator["StaticReq"]
type RuntimeReq = StaticReq | MacroReq | BooleanCombinator["RuntimeReq"]

@dataclass(frozen=True)
class LogicRequirement(abc.ABC):
  @abc.abstractmethod
  def eval(self, logic: "Logic") -> bool: ...

  # Specialize requirements based on specific seed options. 
  @abc.abstractmethod
  def specialize_for_seed(self, logic: "Logic") -> RuntimeReq: ...

@dataclass(frozen=True)
class NothingReq(LogicRequirement):
  @override
  def eval(self, logic: "Logic") -> bool: 
    return True

  @override
  def __str__(self) -> str:
    return "Nothing"

  @override
  def specialize_for_seed(self, logic: "Logic") -> RuntimeReq:
    return self

  T = TypeVar("T", bound=LogicRequirement)
  def simplify_and(self, other: T) -> T:
    return other
  def simplify_or(self, _: LogicRequirement) -> "NothingReq":
    return self

Nothing = NothingReq()

@dataclass(frozen=True)
class ImpossibleReq(LogicRequirement):
  @override
  def eval(self, logic: "Logic") -> bool:
    return False
  
  @override
  def __str__(self) -> str:
    return "Impossible"

  @override
  def specialize_for_seed(self, logic: "Logic") -> RuntimeReq:
    return self

Impossible = ImpossibleReq()

@dataclass(frozen=True)
class BooleanCombinator[T: (LogicRequirement, StaticReq, RuntimeReq)](LogicRequirement, abc.ABC):
  exps: frozenset[T]

  @classmethod
  def from_elements(cls, *args: T) -> Self:
    return cls(frozenset(args))

  @classmethod
  def from_iterable(cls, elems: Iterable[T]) -> Self:
    return cls(frozenset(elems))

@dataclass(frozen=True)
class Or[T: (LogicRequirement, StaticReq, RuntimeReq)](BooleanCombinator[T]):
  @override
  def eval(self, logic: "Logic") -> bool:
    return any(e.eval(logic) for e in self.exps)

  @override
  def specialize_for_seed(self, logic: "Logic") -> RuntimeReq:
    reduced: set[RuntimeReq] = set()
    for e in self.exps:
      simplified = e.specialize_for_seed(logic)
      if simplified is Nothing:
        return Nothing
      elif simplified is Impossible:
        continue
      elif isinstance(simplified, Or):
        reduced |= simplified.exps
      elif isinstance(simplified, ItemReq):
        # Min quantity
        if equiv := next((e for e in reduced if isinstance(e, ItemReq) and e.item == simplified.item), None):
          reduced.remove(equiv)
          reduced.add(ItemReq(simplified.item, min(equiv.num, simplified.num)))
        else:
          reduced.add(simplified)
      elif isinstance(simplified, (MacroReq, BooleanCombinator)):
        reduced.add(simplified)
      else:
        raise ValueError("Unhandled logicrequirement")

    if len(reduced) > 1:
      return Or[RuntimeReq](frozenset(reduced))
    elif len(reduced) == 1:
      return reduced.pop()
    else:
      return Impossible

  @override
  def __str__(self) -> str:
    return " | ".join(
      f"({e})" if isinstance(e, BooleanCombinator) else str(e)
      for e in self.exps
    )

@dataclass(frozen=True)
class And[T: (LogicRequirement, StaticReq, RuntimeReq)](BooleanCombinator[T]):
  @override
  def eval(self, logic: "Logic") -> bool:
    return all(e.eval(logic) for e in self.exps)

  @override
  def specialize_for_seed(self, logic: "Logic") -> RuntimeReq:
    reduced: set[RuntimeReq] = set()
    for e in self.exps:
      simplified = e.specialize_for_seed(logic)
      if simplified is Impossible:
        return Impossible
      elif simplified is Nothing:
        continue
      elif isinstance(simplified, And):
        reduced |= simplified.exps
      elif isinstance(simplified, ItemReq):
        # Max quantity
        if equiv := next((e for e in reduced if isinstance(e, ItemReq) and e.item == simplified.item), None):
          reduced.remove(equiv)
          reduced.add(ItemReq(simplified.item, max(equiv.num, simplified.num)))
        else:
          reduced.add(simplified)
      elif isinstance(simplified, (MacroReq, Or)):
        reduced.add(simplified)
      else:
        raise ValueError("Unhandled logicrequirement")

    if len(reduced) > 1:
      return And[RuntimeReq](frozenset(reduced))
    elif len(reduced) == 1:
      return reduced.pop()
    else:
      return Nothing

  @override
  def __str__(self) -> str:
    return " & ".join(
      f"({e})" if isinstance(e, BooleanCombinator) else str(e)
      for e in self.exps
    )

@dataclass(frozen=True)
class ItemReq(LogicRequirement):
  item: str
  num: int = 1

  @override
  def eval(self, logic: "Logic") -> bool:
    return logic.currently_owned_items.get(self.item, 0) >= self.num

  @override
  def specialize_for_seed(self, logic: "Logic") -> "ItemReq|NothingReq":
    if logic.rando.starting_items.count(self.item) >= self.num:
      return Nothing
    else:
      return self

  @override
  def __str__(self) -> str:
    if self.num > 1:
      return f"{self.item} x{self.num}"
    else:
      return self.item

@dataclass(frozen=True)
class SettingReq(LogicRequirement):
  setting: str
  value: Any

  def __post_init__(self) -> None:
    if not self.setting in Options.by_name:
      raise ValueError(f"Unknown setting {self.setting}")
  
  @override
  def specialize_for_seed(self, logic: "Logic") -> ImpossibleReq|NothingReq:
    return Nothing if self.eval(logic) else Impossible

  @override
  def eval(self, logic: "Logic") -> bool:
    return logic.options[self.setting] == self.value

  @override
  def __str__(self) -> str:
    return f"Option {self.setting} is {self.value}"

@dataclass(frozen=True)
class NegativeSettingReq(SettingReq):
  def __post_init__(self) -> None:
    assert issubclass(Options.by_name[self.setting].type, Enum)
    assert isinstance(self.value, Options.by_name[self.setting].type)
    # self.value = Options.by_name[self.setting].type(self.value) # Frozen dataclass prevents auto converting

  @override
  def eval(self, logic: "Logic") -> bool:
    return logic.options[self.setting] != self.value

  @override
  def __str__(self) -> str:
    return f"Option {self.setting} is not {self.value}"

@dataclass(frozen=True)
class ContainsSettingReq(SettingReq):
  def __post_init__(self) -> None:
    assert Options.by_name[self.setting].type == list

  @override
  def eval(self, logic: "Logic") -> bool:
    return self.value in logic.options[self.setting]

  @override
  def __str__(self) -> str:
    return f"Option {self.setting} contains {self.value}"

@dataclass(frozen=True)
class NotContainsSettingReq(SettingReq):
  def __post_init__(self) -> None:
    assert Options.by_name[self.setting].type == list

  @override
  def eval(self, logic: "Logic") -> bool:
    return self.value not in logic.options[self.setting]

  @override
  def __str__(self) -> str:
    return f"Option {self.setting} does not contain {self.value}"


@dataclass(frozen=True)
class OtherLocationReq(LogicRequirement):
  other_loc: str

  @override
  def eval(self, logic: "Logic") -> bool:
    return logic.item_locations[self.other_loc]["Need"].eval(logic)

  @override
  def specialize_for_seed(self, logic: "Logic") -> RuntimeReq:
    # Note this is susceptible to loops
    return logic.item_locations[self.other_loc]["Need"].specialize_for_seed(logic)

  @override
  def __str__(self) -> str:
    return f'Can Access Other Location "{self.other_loc}"'

@dataclass(frozen=True)
class MacroReq(LogicRequirement):
  macro_name: str

  @override
  def eval(self, logic: "Logic") -> bool:
    return logic.macros[self.macro_name].eval(logic)

  @override
  def specialize_for_seed(self, logic: "Logic") -> RuntimeReq:
    if self.macro_name in logic.mutable_macros:
      return self
    if self.macro_name in logic.macros:
      return logic.macros[self.macro_name].specialize_for_seed(logic)
    return self

  @override
  def __str__(self) -> str:
    return f'[Macro: "{self.macro_name}"]'

TERMINAL_EXPRESSIONS = (ItemReq, SettingReq, NothingReq, ImpossibleReq)