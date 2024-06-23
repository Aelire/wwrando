from collections.abc import Collection, Mapping

from logic.expressions.requirement import TERMINAL_EXPRESSIONS, BooleanCombinator, LogicRequirement, MacroReq, OtherLocationReq

def expr_is_terminal(expr, *, terminal_macros: Collection[str], macro_library: dict[str, LogicRequirement]):
  if isinstance(expr, TERMINAL_EXPRESSIONS):
    return True
  if isinstance(expr, BooleanCombinator):
    return all(expr_is_terminal(subex, terminal_macros=terminal_macros, macro_library=macro_library) for subex in expr.exps)
  if isinstance(expr, OtherLocationReq):
    return False
  if isinstance(expr, MacroReq):
    if not terminal_macros:
      return False
    if expr.macro_name in terminal_macros:
      return True
    return False
  
  raise ValueError(f"Unknown type of logical expression: {type(expr)}")
  
def children(expr: LogicRequirement, *, macro_libary: Mapping[str, LogicRequirement]) -> frozenset[LogicRequirement]:
  if isinstance(expr, TERMINAL_EXPRESSIONS):
    return frozenset()
  elif isinstance(expr, BooleanCombinator):
    return expr.exps
  elif isinstance(expr, MacroReq):
    return frozenset((macro_libary[expr.macro_name],))
  elif isinstance(expr, OtherLocationReq):
    raise ValueError("Unsimplified OtherLocationReq in macro")
  else:
    raise ValueError(f"Unknown type of logical expression: {type(expr)}")
  
class LoopError(Exception): pass
  
def recursive_children(expr: LogicRequirement, *, macro_library: Mapping[str, LogicRequirement], ignore_cycles = False):
  visited = set()
  stack = [expr]
  
  while stack:
    node = stack.pop()
    if node in visited:
      if ignore_cycles:
        continue
      else:
        raise LoopError()
    visited.add(node)

    stack.extend(children(node, macro_libary=macro_library))
  return visited