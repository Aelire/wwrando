from collections.abc import Collection, Mapping

from logic.expressions.requirement import TERMINAL_EXPRESSIONS, And, BooleanCombinator, Impossible, ImpossibleReq, ItemReq, LogicRequirement, MacroReq, MultiItemReq, Nothing, NothingReq, Or, OtherLocationReq, RuntimeReq, StaticReq

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
  
def children(expr: RuntimeReq, *, macro_libary: Mapping[str, RuntimeReq]) -> frozenset[RuntimeReq]:
  if isinstance(expr, TERMINAL_EXPRESSIONS):
    return frozenset()
  elif isinstance(expr, BooleanCombinator):
    return expr.exps
  elif isinstance(expr, MacroReq):
    return frozenset((macro_libary[expr.macro_name],))
  
class LoopError(Exception): pass
  
def recursive_children(expr: RuntimeReq, *, macro_library: Mapping[str, RuntimeReq], ignore_cycles = False):
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


def simplify_or(exp: Or[StaticReq]) -> StaticReq:
  reduced: set[ItemReq] = set()
  ands_to_distribute: set[And[StaticReq]] = set()
  stack = set(exp.exps)
  while stack:
    e = stack.pop()
    if e is Nothing:
      return Nothing
    elif e is Impossible:
      continue
    elif isinstance(e, Or):
      stack |= e.exps
      continue
    elif isinstance(e, And):
      cnf = simplify_and(e)
      if not isinstance(cnf, And):
        stack.add(cnf)
      else:
        ands_to_distribute.add(cnf)
    elif isinstance(e, ItemReq):
      # Min quantity
      if equiv := next((r for r in reduced if e.item == r.item), None):
        reduced.remove(equiv)
        reduced.add(ItemReq(e.item, min(equiv.num, e.num)))
      else:
        reduced.add(e)
  
  # ands_to_distribute is an And of Ors (or StaticReq)
  if ands_to_distribute:
    distributed: set[And] = set()
    for andexpr in ands_to_distribute:
      for subexp in andexpr.exps:
        if isinstance(subexp, ItemReq):
          # TODO: finish this
          raise NotImplementedError()

  if len(reduced) > 1:
    return Or[StaticReq](frozenset(reduced))
  elif len(reduced) == 1:
    return reduced.pop()
  else:
    return Impossible

# Flattens an and expression of static requirements into conjunctive normal form
def simplify_and(exp: And[StaticReq]) -> And[StaticReq]|StaticReq:
  stack = set(exp.exps)
  reduced: set[StaticReq] = set()
  for e in stack:
    if e is Impossible:
      return Impossible
    elif e is Nothing:
      continue
    elif isinstance(e, And):
      stack |= e.exps
    elif isinstance(e, ItemReq):
      # Max quantity
      if equiv := next((e for e in reduced if isinstance(e, ItemReq) and e.item == e.item), None):

        reduced.remove(equiv)
        reduced.add(ItemReq(e.item, max(equiv.num, e.num)))
      else:
        reduced.add(e)
    elif isinstance(e, Or):
      reduced.add(simplify_or(e))
    else:
      raise ValueError("Unhandled logicrequirement")

  if len(reduced) > 1:
    return And[StaticReq].from_iterable(reduced)
  elif len(reduced) == 1:
    return reduced.pop()
  else:
    return Nothing
