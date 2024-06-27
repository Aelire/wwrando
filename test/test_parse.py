from argparse import Namespace
from logic.expressions import parser
from logic.expressions.requirement import LogicRequirement
from options.wwrando_options import Options

def test_parse_all():
  macro_lib = parser.load_and_parse_macros()
  for macro, defn in macro_lib.items():
    print(f"{macro}: {defn}")
  item_locations = parser.load_and_parse_item_locations(known_macros=macro_lib)
  for macro, attrs in item_locations.items():
    print(f"{macro}: {attrs["Need"]}")

class LogicMock:
  item_locations: dict[str, dict]
  macros: dict[str, LogicRequirement]
  mutable_macros: set[str] = set()
  options: Options
  rando = Namespace(starting_items = ["Progressive Sword", "Wind's Requiem", "Boat's Sail", "Wind Waker", "Ballad of Gales"])

def test_parse_all_and_simplify():
  logic = LogicMock()
  logic.options = Options()
  logic.macros = parser.load_and_parse_macros()
  logic.item_locations = parser.load_and_parse_item_locations(known_macros=logic.macros)

  for loc, attrs in logic.item_locations.items():
    opt = attrs["Need"].specialize_for_seed(logic)
    print(f"{loc}: {opt}")

def equivalent(a: str, b: str, macro_library=None, options: Options|None = None) -> bool:
  if options is None:
    options = Options()
  if macro_library is None:
    macro_library = {}
  logic = LogicMock()
  logic.options = options
  logic.macros = macro_library

  parsed_a = parser.parse_logic_expression(a, known_macros=macro_library).specialize_for_seed(logic)
  parsed_b = parser.parse_logic_expression(b, known_macros=macro_library).specialize_for_seed(logic)

  return parsed_a == parsed_b


def test_logic_simplifications():
  assert equivalent("Nothing & Impossible", "Impossible")
  assert equivalent("Impossible & Impossible", "Impossible")
  assert equivalent("Nothing & Nothing", "Nothing")
  assert equivalent("Nothing | Impossible", "Nothing")
  assert equivalent("Impossible | Impossible", "Impossible")
  assert equivalent("Nothing | Nothing", "Nothing")
  assert equivalent( # distribution
    "Bombs & Hookshot & (Progressive Bow & Progressive Sword x2)",
    "Bombs & Hookshot & Progressive Bow & Progressive Sword x2",
  )
  assert equivalent( # Commutative
    "Bombs & Hookshot & (Progressive Bow x2 & Progressive Sword x1)",
    "Hookshot & Progressive Bow x2 & Progressive Sword x1 & Bombs",
  )
  assert equivalent("Progressive Bow x2 & Progressive Bow x1", "Progressive Bow x2")
  assert equivalent("Progressive Bow x2 | Progressive Bow x1", "Progressive Bow x1")
  assert equivalent("DRC Small Key", "DRC Small Key x1")
