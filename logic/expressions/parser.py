from collections.abc import Collection, Iterator
import os
import re
from typing import Any

from ruamel.yaml import YAML
yaml = YAML(typ="safe")

from logic.expressions.requirement import And, ContainsSettingReq, Impossible, ItemReq, LogicRequirement, MacroReq, NegativeSettingReq, NotContainsSettingReq, Nothing, Or, OtherLocationReq, SettingReq
from logic.item_types import ALL_UNIQUE_ITEMS
from options.wwrando_options import Options
from wwrando_paths import LOGIC_PATH

def load_and_parse_item_locations(*, skip_parsing_reqs = False, known_macros: Collection[str]) -> dict[str, dict]:
  with open(os.path.join(LOGIC_PATH, "item_locations.txt")) as f:
    item_locations = yaml.load(f)
  
  for location_name in item_locations:
    if not skip_parsing_reqs:
      req_string = item_locations[location_name]["Need"]
      if req_string is None:
        raise Exception("Requirements are blank for location \"%s\"" % location_name)
      item_locations[location_name]["Need"] = parse_logic_expression(req_string, known_macros=known_macros)
    
    types_string = item_locations[location_name]["Types"]
    types = types_string.split(",")
    types = [type.strip() for type in types]
    item_locations[location_name]["Types"] = types
  
  return item_locations
  
def load_and_parse_macros() -> dict[str, LogicRequirement]:
  with open(os.path.join(LOGIC_PATH, "macros.txt")) as f:
    macro_strings = yaml.load(f)
  
  known_macros = macro_strings.keys()
  # Pre-load the macro names so that references to macros defined later in the file are still valid
  macros = {
    name: parse_logic_expression(req_string, known_macros=known_macros) 
    for name, req_string in macro_strings.items()
  }
  
  return macros
  
def load_and_parse_enemy_locations(known_macros: Collection[str]) -> dict[str, list[dict[str, Any]]]:
  with open(os.path.join(LOGIC_PATH, "enemy_locations.txt")) as f:
    enemy_locations = yaml.load(f)
  
  for name, area in enemy_locations.items():
    for group in area:
      group["Original requirements"] = parse_logic_expression(group["Original requirements"], known_macros=known_macros)
  
  return enemy_locations
  
def parse_logic_expression(string: str, *, known_macros: Collection[str]) -> LogicRequirement:
  tokens = filter(None, (substring.strip() for substring in re.split("([&|()])", string)))
  try:
    exp = parse_stream(tokens, known_macros=known_macros)
    return exp
  except ParseError as e:
    raise ValueError(f'{e}. In expression: "string"') from None
  
class ParseError(Exception):
  def __init__(self, pos: int, *args: object) -> None:
    super().__init__(*args)
    self.pos = pos
  
  def __str__(self) -> str:
    return f"At position {self.pos}: {super().__str__()}"
  
def parse_stream(stream: Iterator[str], *, known_macros: Collection[str]) -> LogicRequirement:
  expression_type = None
  expressions: list[LogicRequirement] = []
  pos = 0
  for token in stream:
    pos += 1
    if token == ")":
      break
    elif token == "(":
      # Advances the stream until next )
      expressions.append(parse_stream(stream, known_macros=known_macros))
    elif token == "|":
      if expression_type == And:
        raise ParseError(pos, f"Error parsing progression requirements: & and | must not be within the same nesting level.")
      expression_type = Or
    elif token == "&":
      if expression_type == Or:
        raise ParseError(pos, f"Error parsing progression requirements: & and | must not be within the same nesting level.")
      expression_type = And
    elif token in known_macros:
      expressions.append(MacroReq(token))
    elif token.startswith("Option "):
      expressions.append(parse_option_requirement(token))
    elif token.startswith("Can Access Item Location \""):
      match = re.search(r"^Can Access Item Location \"([^\"]+)\"$", token)
      assert match, f"Error parsing other location requirement: {token}"
      expressions.append(OtherLocationReq(match.group(1)))
    elif token == "Nothing":
      expressions.append(Nothing)
    elif token == "Impossible":
      expressions.append(Impossible)
    else:
      expressions.append(parse_item_req(token))
  
  if expression_type == Or:
    return Or(frozenset(expressions))
  elif expression_type == And:
    return And(frozenset(expressions))
  else:
    assert len(expressions) == 1
    return expressions[0]

def parse_item_req(item_req: str) -> ItemReq:
  # Helper to parse the various ways of specifying item requirements
  if item_req.startswith("Progressive "):
    match = re.search(r"^(Progressive .+?)(?: x(\d+))?$", item_req)
    assert match, f"Error parsing progressive item requirement: {item_req}"
    return ItemReq(match.group(1), int(match.group(2) or 1))
  if " Small Key x" in item_req:
    match = re.search(r"^(.+ Small Key)(?: x(\d+))?$", item_req)
    assert match, f"Error parsing key requirement: {item_req}"
    return ItemReq(match.group(1), int(match.group(2) or 1))
  else:
    assert item_req in ALL_UNIQUE_ITEMS, f"{item_req} is not a known progress item"
  
  return ItemReq(item_req)

def parse_option_requirement(req_name: str) -> SettingReq:
  if positive_boolean_match := re.search(r"^Option \"([^\"]+)\" Enabled$", req_name):
    option_name = positive_boolean_match.group(1)
    return SettingReq(option_name, True)
  elif negative_boolean_match := re.search(r"^Option \"([^\"]+)\" Disabled$", req_name):
    option_name = negative_boolean_match.group(1)
    return SettingReq(option_name, False)
  elif positive_dropdown_match := re.search(r"^Option \"([^\"]+)\" Is \"([^\"]+)\"$", req_name):
    option_name = positive_dropdown_match.group(1)
    value = positive_dropdown_match.group(2)
    return SettingReq(option_name, Options.by_name[option_name].type(value))
  elif negative_dropdown_match := re.search(r"^Option \"([^\"]+)\" Is Not \"([^\"]+)\"$", req_name):
    option_name = negative_dropdown_match.group(1)
    value = negative_dropdown_match.group(2)
    return NegativeSettingReq(option_name, Options.by_name[option_name].type(value))
  elif positive_list_match := re.search(r"^Option \"([^\"]+)\" Contains \"([^\"]+)\"$", req_name):
    option_name = positive_list_match.group(1)
    value = positive_list_match.group(2)
    return ContainsSettingReq(option_name, value)
  elif negative_list_match := re.search(r"^Option \"([^\"]+)\" Does Not Contain \"([^\"]+)\"$", req_name):
    option_name = negative_list_match.group(1)
    value = negative_list_match.group(2)
    return NotContainsSettingReq(option_name, value)
  else:
    raise Exception("Invalid option check requirement: %s" % req_name)