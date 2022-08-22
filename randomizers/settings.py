from collections import OrderedDict
import random

from randomizer import Randomizer
from logic.logic import Logic
from randomizers import items

DEFAULT_WEIGHTS = OrderedDict({
  "progression_dungeons": [(True, 80), (False, 20)],
  "progression_great_fairies": [(True, 50), (False, 50)],
  "progression_puzzle_secret_caves": [(True, 50), (False, 50)],
  "progression_combat_secret_caves": [(True, 50), (False, 50)],
  "progression_short_sidequests": [(True, 50), (False, 50)],
  "progression_long_sidequests": [(True, 20), (False, 80)],
  "progression_spoils_trading": [(True, 10), (False, 90)],
  "progression_minigames": [(True, 50), (False, 50)],
  "progression_free_gifts": [(True, 80), (False, 20)],
  "progression_mail": [(True, 50), (False, 50)],
  "progression_platforms_rafts": [(True, 50), (False, 50)],
  "progression_submarines": [(True, 50), (False, 50)],
  "progression_eye_reef_chests": [(True, 50), (False, 50)],
  "progression_big_octos_gunboats": [(True, 50), (False, 50)],
  "progression_triforce_charts": [(True, 20), (False, 80)],
  "progression_treasure_charts": [(True, 5), (False, 95)],
  "progression_expensive_purchases": [(True, 20), (False, 80)],
  "progression_misc": [(True, 50), (False, 50)],
  "progression_tingle_chests": [(True, 50), (False, 50)],
  "progression_battlesquid": [(True, 20), (False, 80)],
  "progression_savage_labyrinth": [(True, 35), (False, 65)],
  "progression_island_puzzles": [(True, 50), (False, 50)],
  
  "keylunacy": [(True, 40), (False, 60)],
  "randomize_entrances": [("Disabled", 20), ("Dungeons", 20), ("Secret Caves", 20), ("Dungeons & Secret Caves (Separately)", 20), ("Dungeons & Secret Caves (Together)", 20)],
  "randomize_charts": [(True, 50), (False, 50)],
  "randomize_starting_island": [(True, 100), (False, 0)],
  "chest_type_matches_contents": [(True, 100), (False, 0)],
  "keep_duplicates_in_logic": [(True, 50), (False, 50)],
  
  "num_path_hints": [(6, 100)],
  "num_barren_hints": [(6, 100)],
  "num_location_hints": [(8, 100)],
  "num_item_hints": [(0, 100)],
  "only_use_ganondorf_paths": [(True, 25), (False, 75)],
  "clearer_hints": [(True, 100), (False, 0)],
  "use_always_hints": [(True, 100), (False, 0)],
  
  "swift_sail": [(True, 100), (False, 0)],
  "instant_text_boxes": [(True, 100), (False, 0)],
  "reveal_full_sea_chart": [(True, 100), (False, 0)],
  "num_starting_triforce_shards": [(0, 60), (1, 9), (2, 8), (3, 8), (4, 5), (5, 5), (6, 2), (7, 2), (8, 1)],
  "add_shortcut_warps_between_dungeons": [(True, 80), (False, 20)],
  "do_not_generate_spoiler_log": [(True, 100), (False, 0)],
  "sword_mode": [("Start with Hero's Sword", 60), ("No Starting Sword", 35), ("Swordless", 5)],
  "race_mode": [(True, 90), (False, 10)],
  "num_race_mode_dungeons": [(1, 5), (2, 15), (3, 25), (4, 30), (5, 15), (6, 10)],
  "randomize_music": [(True, 0), (False, 100)],
  "starting_gear": [
    (["Progressive Picto Box"], 5.6),
    (["Spoils Bag"], 5.6),
    (["Grappling Hook"], 5.6),
    (["Progressive Bow"], 5.6),
    (["Power Bracelets"], 5.6),
    (["Iron Boots"], 5.6),
    (["Bait Bag"], 5.6),
    (["Boomerang"], 5.6),
    (["Hookshot"], 5.6),
    (["Bombs"], 5.6),
    (["Skull Hammer"], 5.6),
    (["Deku Leaf"], 5.6),
    (["Progressive Shield"], 5.6),
    (["Empty Bottle"], 5.6),
    (["Ghost Ship Chart"], 5.6),
    (["Progressive Magic Meter"], 5.6),
    (["Nayru's Pearl", "Din's Pearl", "Farore's Pearl"], 5.6),
    (["Delivery Bag"], 1.16),
    (["Delivery Bag", "Note to Mom"], 0.91),
    (["Delivery Bag", "Maggie's Letter"], 0.91),
    (["Delivery Bag", "Moblin's Letter"], 0.91),
    (["Delivery Bag", "Cabana Deed"], 0.91),
  ],
  "starting_pohs": [(0, 100)],
  "starting_hcs": [(0, 100)],
  "remove_music": [(True, 0), (False, 100)],
  "randomize_enemies": [(True, 0), (False, 100)],
  
  "hint_placement": [("fishmen_hints", 0), ("hoho_hints", 10), ("korl_hints", 80), ("stone_tablet_hints", 10)],
  "num_starting_items": [(0, 25), (1, 40), (2, 25), (3, 10)],
  "start_with_maps_and_compasses": [(True, 80), (False, 20)],
})

# add `skip_rematch_bosses` after initialization to ensure `progression_dungeons` is sampled first
DEFAULT_WEIGHTS["skip_rematch_bosses"] = [(True, 75), (False, 25)]

# Initial check "cost" is inversely related to likelihood of setting, with a flat cost of 1 for 50/50 settings
PROGRESSION_SETTINGS_CHECK_COSTS = {
  k: 100 / (2 * v[0][1])
  for k,v in DEFAULT_WEIGHTS.items()
  if k.startswith("progression_")
}

DUNGEON_NONPROGRESS_ITEMS = \
  ["DRC Dungeon Map", "DRC Compass"] + \
  ["FW Dungeon Map", "FW Compass"] + \
  ["TotG Dungeon Map", "TotG Compass"] + \
  ["FF Dungeon Map", "FF Compass"] + \
  ["ET Dungeon Map", "ET Compass"] + \
  ["WT Dungeon Map", "WT Compass"]


def weighted_sample_without_replacement(population, weights, k=1):
  # Perform a weighted sample of `k`` elements from `population` without replacement.
  # Taken from: https://stackoverflow.com/a/43649323
  weights = list(weights)
  positions = range(len(population))
  indices = []
  while True:
    needed = k - len(indices)
    if not needed:
      break
    for i in random.choices(positions, weights, k=needed):
      if weights[i]:
        weights[i] = 0.0
        indices.append(i)
  return [population[i] for i in indices]

def randomize_settings(seed=None):
  random.seed(seed)
  
  settings_dict = {
    "starting_gear": [],
  }
  for option_name, option_values in DEFAULT_WEIGHTS.items():
    values, weights = zip(*option_values)
    
    if option_name == "hint_placement":
      chosen_hint_placement = random.choices(values, weights=weights)[0]
      for hint_placement in values:
        settings_dict[hint_placement] = (hint_placement == chosen_hint_placement)
    elif option_name == "start_with_maps_and_compasses":
      start_with_maps_and_compasses = random.choices(values, weights=weights)[0]
      if start_with_maps_and_compasses:
        settings_dict["starting_gear"] += DUNGEON_NONPROGRESS_ITEMS
    elif option_name == "starting_gear":
      # Randomize starting gear after all the other settings are generated by calling `randomize_starting_gear`
      continue
    elif option_name == "num_starting_items":
      continue
    elif option_name == "skip_rematch_bosses":
      if settings_dict["progression_dungeons"]:
        chosen_option = True
      else:
        chosen_option = random.choices(values, weights=weights)[0]
      settings_dict["skip_rematch_bosses"] = chosen_option
    else:
      chosen_option = random.choices(values, weights=weights)[0]
      settings_dict[option_name] = chosen_option
  
  # Randomize starting gear dynamically based on items which have logical implications in this seed
  settings_dict["starting_gear"] = randomize_starting_gear(settings_dict, seed=seed)
  
  target_checks = 150
  if target_checks > 0: # TODO make this a proper option
    settings_dict = adjust_settings_to_target(settings_dict, target_checks)

  return settings_dict

def randomize_starting_gear(options, seed=None):
  starting_gear = ["Telescope", "Ballad of Gales", "Song of Passing"]
  
  values, weights = zip(*DEFAULT_WEIGHTS["num_starting_items"])
  num_starting_items = random.choices(values, weights=weights)[0]
  if num_starting_items == 0:
    return starting_gear
  
  try:
    rando = Randomizer(seed, "", "", "", options, cmd_line_args={"-dry": None})
  except Exception:
    return starting_gear
  
  # Determine which members of the starting items pool are valid based on their CTMC chest type
  valid_starting_gear_indices = []
  excess_weight = 0
  for i, (gear, weight) in enumerate(DEFAULT_WEIGHTS["starting_gear"]):
    if any(items.get_ctmc_chest_type_for_item(rando, item_name) for item_name in gear):
      valid_starting_gear_indices.append(i)
    else:
      excess_weight += weight
  
  if len(valid_starting_gear_indices) == 0:
    return starting_gear
  
  # Filter out starting items with no logical use and distribute its weight evenly across remaining options
  modified_pool = []
  distributed_weight = excess_weight / len(valid_starting_gear_indices)
  for i, (gear, weight) in enumerate(DEFAULT_WEIGHTS["starting_gear"]):
    if i in valid_starting_gear_indices:
      modified_pool.append((gear, weight + distributed_weight))
  
  values, weights = zip(*modified_pool)
  num_starting_items = min(num_starting_items, len(modified_pool))
  for selected_items in weighted_sample_without_replacement(values, weights, k=num_starting_items):
    starting_gear += selected_items
  
  return list(set(starting_gear))

def get_incremental_locations_for_setting(cached_item_locations, all_options, incremental_option):
  options = all_options.copy()

  options[incremental_option] = False
  before = Logic.get_num_progression_locations_static(cached_item_locations, options)
  options[incremental_option] = True
  after = Logic.get_num_progression_locations_static(cached_item_locations, options)

  #print(f"{incremental_option} is {after - before} checks")
  return after - before

def compute_weighted_locations(settings_dict):
  cached_item_locations = Logic.load_and_parse_item_locations()
  location_cost = lambda opt: int(settings_dict[opt]) * get_incremental_locations_for_setting(cached_item_locations, settings_dict, opt)

  # As the base case, we compute a total "cost" which is the number of checks in
  # a setting times a weight intented to convey the penibility of the setting
  total_cost = sum(
    PROGRESSION_SETTINGS_CHECK_COSTS[s] * location_cost(s)
    for s, value in settings_dict.items() if s.startswith("progression_")
  )

  combat_caves_cost = location_cost("progression_combat_secret_caves")
  secret_caves_cost = location_cost("progression_puzzle_secret_caves")
  if combat_caves_cost+secret_caves_cost > 0 and settings_dict["randomize_entrances"] not in ("Disabled", "Dungeons"):
    # If only one of combat, secret caves are enabled, randomize entrances is
    # "worse" as it can get you to an ool location and be a waste of time
    # If both are enabled, it's not as bad since any entrance is probably a place you'd have needed to visit anyway

    # Since we already counted them as a full 1 in base_weight, this is "on top". so a 1 additional_multiplier is a total of 2 for the weight
    if combat_caves_cost == 0 or secret_caves_cost == 0:
      additional_multiplier = 0.75
      # If dungeons are also in the pool together, but aren't enabled, there's even more dead entrances so bump it a little more
      if settings_dict["randomize_entrances"] == "Dungeons & Secret Caves (Together)" and not settings_dict["progression_dungeons"]:
        additional_multiplier = 1
    else:
      additional_multiplier = 0.25
      if settings_dict["randomize_entrances"] == "Dungeons & Secret Caves (Together)" and not settings_dict["progression_dungeons"]:
        additional_multiplier = 0.40

    total_cost += (combat_caves_cost+secret_caves_cost) * additional_multiplier

  if settings_dict["sword_mode"] == "Swordless":
    # Bump the cost of combat caves when you have a higher likelihood of having to clear them without sword
    total_cost += 1 * combat_caves_cost
  elif settings_dict["sword_mode"] == "No Starting Sword":
    total_cost += 0.15 * combat_caves_cost

  if settings_dict["progression_dungeons"]:
    # Adjust for dungeons: If dungeons are on, put a sliding scale from 0.15 to 0.8
    # depending on the number of race mode dungeons. Ideally we'd be able to
    # independently select which dungeons we want in logic but that'll do for now
    # Since each race mode dungeon means one less item in the item pool (boss
    # reward), each additional dungeon costs "less"
    # Non-race mode has none of that but you may avoid entering some of the
    # dungeons so is less than 6DRM
    DUNGEON_COSTS = [0, 0.20, 0.38, 0.56, 0.74, 0.92, 1.1]
    dungeon_total_cost = location_cost("progression_dungeons") * PROGRESSION_SETTINGS_CHECK_COSTS["progression_dungeons"]
    # Remove dungeons from the initial cost calculation; we'll recompute after the multipliers
    total_cost -= dungeon_total_cost
    if settings_dict["race_mode"]:
      # Apply this first, before any other multiplier. ie this is multiplicative while the others are additive
      dungeon_total_cost *= DUNGEON_COSTS[settings_dict["num_race_mode_dungeons"]]
    # Keylunacy means more items, and more potential dips in dungeons. Apply a flat multiplier
    if settings_dict["keylunacy"]:
      dungeon_total_cost *= 1.2
    # Small cost bump for dungeons randomized entrances
    if settings_dict["randomize_entrances"] in ("Dungeons", "Dungeons & Secret Caves (Separately)") :
      dungeon_total_cost *= 1.05 
    # Larger cost bump for dungeons randomized together with caves, and even larger if
    # randomized with entrances to out-of-logic locations without race mode
    elif settings_dict["randomize_entrances"] == "Dungeons & Secret Caves (Together)":
      if settings_dict["race_mode"]:
        # minimal bump: in race mode we know where the entrances are immediately anyway
        dungeon_total_cost *= 1.05
      else:
        dungeon_total_cost *= 1.1
        # Additional weights for when entrances are mixed with places you don't
        # need to go to anyway
        if combat_caves_cost == 0:
          dungeon_total_cost *= 1.1
        if secret_caves_cost == 0:
          dungeon_total_cost *= 1.15
    # Another bump for missing warp pots
    if not settings_dict["add_shortcut_warps_between_dungeons"]:
      dungeon_total_cost *= 1.1
    if settings_dict["sword_mode"] == "Swordless":
      dungeon_total_cost *= 1.15

    total_cost += dungeon_total_cost

  charts_cost = location_cost("progression_treasure_charts") + location_cost("progression_triforce_charts")
  if settings_dict["randomize_charts"]:
    # Symbolic weight boost for randomized charts, but not higher since nobody
    # knows vanilla locations anyway so it doesn't matter
    total_cost += charts_cost * 0.05 

  return total_cost


ADJUSTABLE_SETTINGS = list(PROGRESSION_SETTINGS_CHECK_COSTS.keys()) + [
  "race_mode",
  "randomize_charts",
  "add_shortcut_warps_between_dungeons",
  # These are special, as they are multivalued
  "sword_mode",
  "randomize_entrances",
  "num_race_mode_dungeons", "num_race_mode_dungeons", # Since this is the most powerful adjustment, retry it a couple times
  # Retry flipping dungeons multiple times since other options have impacts on this too
  "progression_dungeons", "progression_dungeons", "progression_dungeons", 
]
def adjust_settings_to_target(settings_dict, target_checks):
  target_hi, target_lo = int(target_checks * 1.2), int(target_checks * 0.8)
  print(f"Acceptable cost range: {target_lo} to {target_hi}")
  remaining_adjustable_settings = ADJUSTABLE_SETTINGS.copy()
  second_pass_settings = []
  second_pass = False
  random.shuffle(remaining_adjustable_settings)

  while not (target_lo < (current_cost := compute_weighted_locations(settings_dict)) < target_hi):
    current_distance = abs(current_cost - target_checks)
    print(f"At {current_cost}, distance to {target_checks}: {current_distance}")

    if len(remaining_adjustable_settings) > 0 and len(second_pass_settings) > 0 and second_pass is False:
      remaining_adjustable_settings = second_pass_settings
      second_pass = True
    elif len(remaining_adjustable_settings) == 0:
      print("Could not get within target checks! better luck next time")
      break

    selected = remaining_adjustable_settings.pop()

    print(f"Considering {selected} (currently: {settings_dict[selected]})")
    # Small simplification, if there are only 2 options (yes/no) just try the other one
    # and see if it improves
    # for multivalued options we'll have to try a bit more interestingly
    if len(DEFAULT_WEIGHTS[selected]) == 2:
      settings_dict[selected] = not settings_dict[selected]
      new_cost = compute_weighted_locations(settings_dict)
      if abs(new_cost - target_checks) >= current_distance: # This is not getting us closer, revert
        settings_dict[selected] = not settings_dict[selected]

    # For multivalued options, we'll take the "best" one, that takes us closest to the target score
    # With the exception that if it doesn't change anything, we'll requeue it to retry last
    # Because all these options affect dungeons, this gives a chance for
    # dungeons to be enabled, then this will be retried
    else:
      option_scores = {}
      for value, _ in DEFAULT_WEIGHTS[selected]:
        settings_dict[selected] = value
        option_scores[value] = abs(compute_weighted_locations(settings_dict) - target_checks)

      settings_dict[selected] = min(option_scores.items(), key=lambda tup: tup[1])[0]

    print(f"Set {selected} to {settings_dict[selected]}")

  print(f"Final cost: {current_cost}")
  print(f"Final Settings: {settings_dict}")
  return settings_dict

