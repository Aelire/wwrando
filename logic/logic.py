from __future__ import annotations
from typing import TYPE_CHECKING


if TYPE_CHECKING:
  from collections.abc import Mapping
  from randomizer import WWRandomizer

import copy
from contextlib import contextmanager

from logic.expressions.graph_ops import recursive_children, expr_is_terminal
from logic.expressions.requirement import And, Impossible, ItemReq, LogicRequirement, MacroReq, Nothing, OtherLocationReq
from logic.expressions.parser import load_and_parse_item_locations, load_and_parse_macros
from logic.item_types import PROGRESS_ITEMS, NONPROGRESS_ITEMS, CONSUMABLE_ITEMS, DUPLICATABLE_CONSUMABLE_ITEMS, DUNGEON_PROGRESS_ITEMS, DUNGEON_NONPROGRESS_ITEMS
from wwrando_paths import LOGIC_PATH
from randomizers import entrances
from options.wwrando_options import Options, SwordMode

class Logic:
  DUNGEON_NAMES = {
    "DRC" : "Dragon Roost Cavern",
    "FW"  : "Forbidden Woods",
    "TotG": "Tower of the Gods",
    "FF"  : "Forsaken Fortress",
    "ET"  : "Earth Temple",
    "WT"  : "Wind Temple",
  }
  DUNGEON_NAME_TO_SHORT_DUNGEON_NAME = {v: k for k, v in DUNGEON_NAMES.items()}
  
  initial_item_locations = None
  initial_macros = None

  COMPLETE_GAME_REQ = MacroReq("Can Reach and Defeat Ganondorf")
  
  def __init__(self, rando: WWRandomizer):
    self.rando = rando
    self.options = rando.options
    
    # Caches.
    self.cached_enemies_tested_for_reqs_tuple = {}
    
    # Locations and requirements.
    if not self.initial_macros:
      Logic.initial_macros = load_and_parse_macros()
    if not self.initial_item_locations:
      Logic.initial_item_locations = load_and_parse_item_locations(known_macros=Logic.initial_macros)
    self.register_mutable_macros()
    self.item_locations = copy.deepcopy(Logic.initial_item_locations)
    self.compile_macros(Logic.initial_macros.copy())
    for loc in self.item_locations:
      self.item_locations[loc]["Need"] = self.item_locations[loc]["Need"].specialize_for_seed(self)
    
    self.nested_entrance_macros: dict[str, str] = {}
    
    self.locations_by_zone_name: dict[str, list] = {}
    for location_name in self.item_locations:
      zone_name, _ = self.split_location_name_by_zone(location_name)
      if zone_name not in self.locations_by_zone_name:
        self.locations_by_zone_name[zone_name] = []
      self.locations_by_zone_name[zone_name].append(location_name)
    
    self.remaining_item_locations = list(self.item_locations.keys())
    self.prerandomization_item_locations = {}
    
    self.done_item_locations: dict[str, str | None] = {}
    for location_name in self.item_locations:
      self.done_item_locations[location_name] = None
    
    self.rock_spire_shop_ship_locations = []
    for location_name in self.item_locations:
      if location_name.startswith("Rock Spire Isle - Beedle's Special Shop Ship - "):
        self.rock_spire_shop_ship_locations.append(location_name)
    
    
    # Initialize item related attributes.
    self.all_progress_items = PROGRESS_ITEMS.copy()
    self.all_nonprogress_items = NONPROGRESS_ITEMS.copy()
    self.all_fixed_consumable_items = CONSUMABLE_ITEMS.copy()
    self.duplicatable_consumable_items = DUPLICATABLE_CONSUMABLE_ITEMS.copy()
    
    self.triforce_chart_names = []
    self.treasure_chart_names = []
    for i in range(1, 8+1):
      self.triforce_chart_names.append("Triforce Chart %d" % i)
    for i in range(1, 41+1):
      self.treasure_chart_names.append("Treasure Chart %d" % i)
    
    if self.options.sword_mode == SwordMode.SWORDLESS:
      self.all_progress_items = [
        item_name for item_name in self.all_progress_items
        if item_name != "Progressive Sword"
      ]
      self.all_nonprogress_items = [
        item_name for item_name in self.all_nonprogress_items
        if item_name != "Hurricane Spin"
      ]
    
    if self.options.progression_triforce_charts:
      self.all_progress_items += self.triforce_chart_names
    else:
      self.all_nonprogress_items += self.triforce_chart_names
    if self.options.progression_treasure_charts:
      self.all_progress_items += self.treasure_chart_names
    else:
      self.all_nonprogress_items += self.treasure_chart_names
    
    # Add dungeon items to the progress/nonprogress items lists.
    if self.options.progression_dungeons:
      self.all_progress_items += DUNGEON_PROGRESS_ITEMS
    else:
      self.all_nonprogress_items += DUNGEON_PROGRESS_ITEMS
    self.all_nonprogress_items += DUNGEON_NONPROGRESS_ITEMS
    
    if self.options.trap_chests:
      self.all_progress_items += ["Ice Trap Chest"]*5
    
    self.all_cleaned_item_names = []
    all_item_names = []
    all_item_names += self.all_progress_items
    all_item_names += self.all_nonprogress_items
    all_item_names += self.all_fixed_consumable_items
    all_item_names += self.duplicatable_consumable_items
    for item_name in all_item_names:
      cleaned_item_name = self.clean_item_name(item_name)
      if cleaned_item_name not in self.all_cleaned_item_names:
        self.all_cleaned_item_names.append(cleaned_item_name)
    
    self.unplaced_progress_items: list[str]
    self.unplaced_nonprogress_items: list[str]
    self.unplaced_fixed_consumable_items: list[str]
    self.currently_owned_items: dict[str, int] = {}
    
    if self.rando.fully_initialized:
      self.initialize_from_randomizer_state()
  
  def initialize_from_randomizer_state(self):
    self.nested_entrance_macros.clear()
    for zone_entrance in entrances.ZoneEntrance.all.values():
      if zone_entrance.is_nested:
        zone_exit = zone_entrance.nested_in
        entrance_access_macro_name = "Can Access " + zone_entrance.entrance_name
        zone_access_macro_name = "Can Access " + zone_exit.unique_name
        self.nested_entrance_macros[entrance_access_macro_name] = zone_access_macro_name
    
    self.update_entrance_connection_macros()
    self.update_chart_macros()
    
    self.unplaced_progress_items = self.all_progress_items.copy()
    self.unplaced_nonprogress_items = self.all_nonprogress_items.copy()
    self.unplaced_fixed_consumable_items = self.all_fixed_consumable_items.copy()
    self.currently_owned_items.clear()
    
    for item_name in self.rando.starting_items:
      self.add_owned_item(item_name)
    
    # Decide what will count as a progress item on these settings.
    self.make_useless_progress_items_nonprogress()
    
    # Add the randomly-selected extra starting items (without incidence on other progress items).
    if self.rando.extra_start_items.is_enabled():
      for item in self.rando.extra_start_items.random_starting_items:
        # Needs to happen after make useless_progress_items_nonprogress to ensure other progress
        # items aren't made nonprogress by the extra random items being in the starting inventory
        # for the purpose of hints or spoiler log progression.
        self.add_owned_item(item)
    
    self.cached_enemies_tested_for_reqs_tuple.clear()
  
  def save_simulated_playthrough_state(self):
    vars_backup = {}
    for attr_name in [
      "currently_owned_items",
      "unplaced_progress_items",
      "unplaced_nonprogress_items",
      "unplaced_fixed_consumable_items",
    ]:
      vars_backup[attr_name] = copy.deepcopy(getattr(self, attr_name))
    return vars_backup
  
  def load_simulated_playthrough_state(self, vars_backup):
    for attr_name, value in vars_backup.items():
      setattr(self, attr_name, copy.deepcopy(value))
  
  def set_location_to_item(self, location_name, item_name):
    #print("Setting %s to %s" % (location_name, item_name))
    
    if self.done_item_locations[location_name]:
      raise Exception("Location was used twice: " + location_name)
    
    self.done_item_locations[location_name] = item_name
    self.remaining_item_locations.remove(location_name)
    
    self.add_owned_item(item_name)
  
  def set_prerandomization_item_location(self, location_name, item_name):
    # Temporarily keep track of where certain items are placed before the main progression item randomization loop starts.
    
    #print("Setting prerand %s to %s" % (location_name, item_name))
    
    assert location_name in self.item_locations
    self.prerandomization_item_locations[location_name] = item_name
  
  def get_num_progression_locations(self):
    return Logic.get_num_progression_locations_static(self.item_locations, self.options)
  
  @staticmethod
  def get_num_progression_locations_static(item_locations: dict[str, dict], options: Options):
    progress_locations = Logic.filter_locations_for_progression_static(
      list(item_locations.keys()),
      item_locations,
      options,
      filter_sunken_treasure=True
    )
    num_progress_locations = len(progress_locations)
    if options.progression_triforce_charts:
      num_progress_locations += 8
    if options.progression_treasure_charts:
      num_progress_locations += 41
    
    return num_progress_locations
  
  def get_max_required_bosses_banned_locations(self):
    if not self.options.required_bosses:
      return 0
    
    all_locations = list(self.item_locations.keys())
    progress_locations = self.filter_locations_for_progression(all_locations)
    location_counts_by_dungeon = {}
    
    for location_name in progress_locations:
      zone_name, _ = self.split_location_name_by_zone(location_name)
      
      dungeon_name = None
      if self.is_dungeon_location(location_name):
        dungeon_name = zone_name
      elif location_name == "Mailbox - Letter from Orca":
        dungeon_name = "Forbidden Woods"
      elif location_name == "Mailbox - Letter from Baito":
        dungeon_name = "Earth Temple"
      elif location_name == "Mailbox - Letter from Aryll":
        dungeon_name = "Forsaken Fortress"
      elif location_name == "Mailbox - Letter from Tingle":
        dungeon_name = "Forsaken Fortress"
      
      if dungeon_name is None:
        continue
      
      if dungeon_name in location_counts_by_dungeon:
        location_counts_by_dungeon[dungeon_name] += 1
      else:
        location_counts_by_dungeon[dungeon_name] = 1
    
    dungeon_location_counts = list(location_counts_by_dungeon.values())
    dungeon_location_counts.sort(reverse=True)
    num_banned_dungeons = 6 - self.options.num_required_bosses
    max_banned_locations = sum(dungeon_location_counts[:num_banned_dungeons])
    
    return max_banned_locations
  
  def get_progress_and_non_progress_locations(self):
    all_locations = list(self.item_locations.keys())
    progress_locations = self.filter_locations_for_progression(all_locations, filter_sunken_treasure=True)
    nonprogress_locations = []
    for location_name in all_locations:
      if location_name in progress_locations:
        continue
      
      types = self.item_locations[location_name]["Types"]
      if "Sunken Treasure" in types:
        chart_name = self.chart_name_for_location(location_name)
        if "Triforce Chart" in chart_name:
          if self.options.progression_triforce_charts:
            progress_locations.append(location_name)
          else:
            nonprogress_locations.append(location_name)
        else:
          if self.options.progression_treasure_charts:
            progress_locations.append(location_name)
          else:
            nonprogress_locations.append(location_name)
      else:
        nonprogress_locations.append(location_name)
    
    return (progress_locations, nonprogress_locations)
  
  def add_owned_item(self, item_name):
    cleaned_item_name = self.clean_item_name(item_name)
    if cleaned_item_name not in self.all_cleaned_item_names:
      raise Exception("Unknown item name: " + item_name)
    
    self.currently_owned_items[cleaned_item_name] = self.currently_owned_items.get(cleaned_item_name, 0) + 1
    
    if item_name in self.unplaced_progress_items:
      self.unplaced_progress_items.remove(item_name)
    elif item_name in self.unplaced_nonprogress_items:
      self.unplaced_nonprogress_items.remove(item_name)
    elif item_name in self.unplaced_fixed_consumable_items:
      self.unplaced_fixed_consumable_items.remove(item_name)
    
  def remove_owned_item(self, item_name):
    cleaned_item_name = self.clean_item_name(item_name)
    if cleaned_item_name not in self.all_cleaned_item_names:
      raise Exception("Unknown item name: " + item_name)
    
    self.currently_owned_items[cleaned_item_name] -= 1
    if self.currently_owned_items[cleaned_item_name] == 0:
      del self.currently_owned_items[cleaned_item_name]
    
    if self.all_progress_items.count(item_name) > self.unplaced_progress_items.count(item_name):
      self.unplaced_progress_items.append(item_name)
    elif item_name in self.all_nonprogress_items:
      self.unplaced_nonprogress_items.append(item_name)
    else:
      # Removing consumable items doesn't work because we don't know if the item is from the fixed list or the duplicatable list
      raise Exception("Cannot remove item from simulated inventory: %s" % item_name)
    
  @contextmanager
  def add_temporary_items(self, item_names):
    for item_name in item_names:
      self.add_owned_item(item_name)
    
    yield
    
    for item_name in item_names:
      self.remove_owned_item(item_name)
  
  def get_accessible_remaining_locations(self, *, for_progression):
    accessible_location_names = []
    
    locations_to_check = self.remaining_item_locations
    if for_progression:
      locations_to_check = self.filter_locations_for_progression(locations_to_check)
    
    for location_name in locations_to_check:
      if self.check_location_accessible(location_name):
        accessible_location_names.append(location_name)
    
    return accessible_location_names
  
  def get_first_useful_item(self, items_to_check):
    # Searches through a given list of items and returns the first one that opens up at least 1 new location.
    # The randomizer shuffles the list before passing it to this function, so in effect it picks a random useful item.
    
    accessible_undone_locations = self.get_accessible_remaining_locations(for_progression=True)
    inaccessible_undone_item_locations = []
    locations_to_check = self.remaining_item_locations
    locations_to_check = self.filter_locations_for_progression(locations_to_check)
    for location_name in locations_to_check:
      if location_name not in accessible_undone_locations:
        inaccessible_undone_item_locations.append(location_name)
    
    # Cache whether each item is useful in order to avoid an absurd number of duplicate recursive calls when checking if a predetermined dungeon item location has a useful item or not.
    self.cached_items_are_useful = {}
    
    for item_name in items_to_check:
      if self.check_item_is_useful(item_name, inaccessible_undone_item_locations):
        self.cached_items_are_useful = None
        return item_name
    
    self.cached_items_are_useful = None
    
    return None
  
  def get_items_by_usefulness_fraction(self, item_names_to_check, *, filter_sunken_treasure):
    # Takes a list of items and locations, and determines for each item what the lowest number of items including it the player needs before a new location is opened up, and returns that in a dict.
    # For example, say there are 3 items A B and C, and 2 locations X and Y.
    # Location X requires items A and B while location Y requires items A B and C.
    # This function would return {A: 2, B: 2, C: 3} because A requires 1 other item (B) to help access anything, B also requires one other item (A) to help access anything, but C requires 2 other items (both A and B) before it becomes useful.
    # In other words, items A and B have 1/2 usefulness, while item C has 1/3 usefulness.
    
    accessible_undone_locations = self.get_accessible_remaining_locations(for_progression=True)
    inaccessible_undone_item_locations = []
    locations_to_check = self.remaining_item_locations
    locations_to_check = self.filter_locations_for_progression(locations_to_check, filter_sunken_treasure=filter_sunken_treasure)
    for location_name in locations_to_check:
      if location_name not in accessible_undone_locations:
        if location_name in self.rando.boss_reqs.banned_locations:
          # Don't consider locations inside unchosen dungeons in required bosses mode when calculating usefulness.
          continue
        if location_name in self.prerandomization_item_locations:
          # We just ignore items with predetermined items when calculating usefulness fractions.
          # TODO: In the future, we might want to consider recursively checking if the item here is useful, and if so include this location.
          continue
        inaccessible_undone_item_locations.append(location_name)
    
    # Generate a list of what items are needed for each inaccessible location (+beating the game).
    # Note: Performance could be improved somewhat by only calculating which items are needed for each location at the start of item randomization, instead of once per call to this function. But this seems unnecessary.
    item_names_for_all_locations = []
    for location_name in inaccessible_undone_item_locations:
      item_names_for_loc = self.get_item_names_by_req(self.item_locations[location_name]["Need"])
      item_names_for_all_locations.append(item_names_for_loc)
    item_names_to_beat_game = self.get_item_names_by_req(self.COMPLETE_GAME_REQ)
    item_names_for_all_locations.append(item_names_to_beat_game)
    
    # Now calculate the best case scenario usefulness fraction for all items given.
    item_by_usefulness_fraction = {}
    for item_name in item_names_to_check:
      item_by_usefulness_fraction[item_name] = 9999
    
    for item_names_for_loc in item_names_for_all_locations:
      item_names_for_loc_without_owned = item_names_for_loc.copy()
      for item_name, num_items in self.currently_owned_items.items():
        for i in range(num_items):
          if item_name in item_names_for_loc_without_owned:
            item_names_for_loc_without_owned.remove(item_name)
      
      for item_name in item_names_for_loc_without_owned:
        if item_name not in item_by_usefulness_fraction:
          continue
        usefulness_fraction_for_item = len(item_names_for_loc_without_owned)
        if usefulness_fraction_for_item < item_by_usefulness_fraction[item_name]:
          item_by_usefulness_fraction[item_name] = usefulness_fraction_for_item
    
    return item_by_usefulness_fraction
  
  def get_all_useless_items(self, items_to_check):
    # Searches through a given list of items and returns which of them do not open up even 1 new location.
    
    if len(items_to_check) == 0:
      return []
    
    accessible_undone_locations = self.get_accessible_remaining_locations(for_progression=True)
    inaccessible_undone_item_locations = []
    locations_to_check = self.remaining_item_locations
    locations_to_check = self.filter_locations_for_progression(locations_to_check)
    for location_name in locations_to_check:
      if location_name not in accessible_undone_locations:
        inaccessible_undone_item_locations.append(location_name)
    
    self.cached_items_are_useful = {}
    
    useless_items = []
    for item_name in items_to_check:
      if not self.check_item_is_useful(item_name, inaccessible_undone_item_locations):
        useless_items.append(item_name)
    
    self.cached_items_are_useful = None
    
    return useless_items
  
  def check_item_is_useful(self, item_name, inaccessible_undone_item_locations):
    # Checks whether a specific item unlocks any new locations or not.
    # This function should only be called by get_first_useful_item, get_all_useless_items, or by itself for recursion purposes.
    
    if item_name in self.cached_items_are_useful:
      return self.cached_items_are_useful[item_name]
    
    self.add_owned_item(item_name)
    
    for location_name in inaccessible_undone_item_locations:
      if location_name in self.rando.boss_reqs.banned_locations:
        # Don't consider locations inside unchosen dungeons in required bosses mode when calculating usefulness.
        continue
      
      if location_name in self.prerandomization_item_locations:
        # If this location has a predetermined item in it, we need to recursively check if that item is useful.
        unlocked_prerand_item = self.prerandomization_item_locations[location_name]
        # Need to exclude the current location from recursive checks to prevent infinite recursion.
        temp_inaccessible_undone_item_locations = [
          loc for loc in inaccessible_undone_item_locations
          if not loc == location_name
        ]
        if not self.check_item_is_useful(unlocked_prerand_item, temp_inaccessible_undone_item_locations):
          # If that item is not useful, don't consider the current item useful for unlocking it.
          continue
        
        if self.check_location_accessible(location_name):
          self.remove_owned_item(item_name)
          self.cached_items_are_useful[item_name] = True
          return True
      
      if self.check_location_accessible(location_name):
        self.remove_owned_item(item_name)
        self.cached_items_are_useful[item_name] = True
        return True
    
    self.remove_owned_item(item_name)
    self.cached_items_are_useful[item_name] = False
    return False
  
  def filter_locations_for_progression(self, locations_to_filter: list[str], filter_sunken_treasure=False):
    return Logic.filter_locations_for_progression_static(
      locations_to_filter,
      self.item_locations,
      self.options,
      filter_sunken_treasure=filter_sunken_treasure
    )
  
  @staticmethod
  def filter_locations_for_progression_static(locations_to_filter: list[str], item_locations: dict[str, dict], options: Options, filter_sunken_treasure=False):
    filtered_locations = []
    for location_name in locations_to_filter:
      types = item_locations[location_name]["Types"]
      if "No progression" in types:
        continue
      if "Consumables only" in types:
        continue
      if "Dungeon" in types and not options.progression_dungeons:
        continue
      if "Tingle Chest" in types and not options.progression_tingle_chests:
        continue
      if "Great Fairy" in types and not options.progression_great_fairies:
        continue
      if "Puzzle Secret Cave" in types and not options.progression_puzzle_secret_caves:
        continue
      if "Combat Secret Cave" in types and not options.progression_combat_secret_caves:
        continue
      if "Savage Labyrinth" in types and not options.progression_savage_labyrinth:
        continue
      if "Short Sidequest" in types and not options.progression_short_sidequests:
        continue
      if "Long Sidequest" in types and not options.progression_long_sidequests:
        continue
      if "Spoils Trading" in types and not options.progression_spoils_trading:
        continue
      if "Minigame" in types and not options.progression_minigames:
        continue
      if "Battlesquid" in types and not options.progression_battlesquid:
        continue
      if "Free Gift" in types and not options.progression_free_gifts:
        continue
      if "Mail" in types and not options.progression_mail:
        continue
      if ("Platform" in types or "Raft" in types) and not options.progression_platforms_rafts:
        continue
      if "Submarine" in types and not options.progression_submarines:
        continue
      if "Eye Reef Chest" in types and not options.progression_eye_reef_chests:
        continue
      if ("Big Octo" in types or "Gunboat" in types) and not options.progression_big_octos_gunboats:
        continue
      if "Expensive Purchase" in types and not options.progression_expensive_purchases:
        continue
      if "Island Puzzle" in types and not options.progression_island_puzzles:
        continue
      if ("Other Chest" in types or "Misc" in types) and not options.progression_misc:
        continue
      if "Dungeon Secret" in types and not options.progression_dungeon_secrets:
        continue
      
      # Note: The Triforce/Treasure Chart sunken treasures are handled differently from other types.
      # During randomization they are handled by not considering the charts themselves to be progress items.
      # That results in the item randomizer considering these locations inaccessible until after all progress items are placed.
      # But when calculating the total number of progression locations, sunken treasures are filtered out entirely here so they can be specially counted elsewhere.
      if "Sunken Treasure" in types and filter_sunken_treasure:
        continue
      
      filtered_locations.append(location_name)
    
    return filtered_locations
  
  def check_item_valid_in_location(self, item_name: str, location_name: str):
    types = self.item_locations[location_name]["Types"]
    paths = self.item_locations[location_name]["Paths"]
    
    # Don't allow dungeon items to appear outside their proper dungeon when Key-Lunacy is off.
    if self.is_dungeon_item(item_name) and not self.options.keylunacy:
      short_dungeon_name = item_name.split(" ")[0]
      dungeon_name = self.DUNGEON_NAMES[short_dungeon_name]
      if not self.is_dungeon_location(location_name, dungeon_name_to_match=dungeon_name):
        return False
      if "Boss" in types:
        # Don't allow dungeon items to be placed on the dungeon boss.
        return False
      if "Randomizable Miniboss Room" in types and self.options.randomize_miniboss_entrances:
        # Don't allow dungeon items to be placed in miniboss rooms when they are randomized.
        return False
    
    # Beedle's shop does not work properly if the same item is in multiple slots of the same shop.
    # Ban the Bait Bag slot from having bait.
    if location_name == "The Great Sea - Beedle's Shop Ship - 20 Rupee Item" and item_name in ["All-Purpose Bait", "Hyoi Pear"]:
      return False
    
    # Also ban the same item from appearing more than once in the rock spire shop ship.
    if location_name in self.rock_spire_shop_ship_locations:
      for other_location_name in self.rock_spire_shop_ship_locations:
        if other_location_name == location_name:
          continue
        if other_location_name in self.done_item_locations:
          other_item_name = self.done_item_locations[other_location_name]
          if item_name == other_item_name:
            return False
    
    # Our code to fix Zunari's Magic Armor item gift relies on the items Zunari gives all having different IDs.
    # Therefore we don't allow the other two items Zunari gives to be placed in the Magic Armor slot.
    if location_name == "Windfall Island - Zunari - Stock Exotic Flower in Zunari's Shop" and item_name in ["Town Flower", "Boat's Sail"]:
      return False
    
    if "Consumables only" in types:
      if item_name not in self.all_fixed_consumable_items and item_name not in self.duplicatable_consumable_items:
        return False
      
    if item_name.endswith(" Trap Chest"):
      if not all(path.split("/")[-1].startswith("Chest") for path in paths):
        return False
    
    return True
  
  def filter_items_by_any_valid_location(self, items, locations):
    # Filters out items that cannot be in any of the given possible locations.
    valid_items = []
    for item_name in items:
      for location_name in locations:
        if self.check_item_valid_in_location(item_name, location_name):
          valid_items.append(item_name)
          break
    return valid_items
  
  def filter_locations_valid_for_item(self, locations, item_name):
    valid_locations = []
    for location_name in locations:
      if self.check_item_valid_in_location(item_name, location_name):
        valid_locations.append(location_name)
    return valid_locations
  
  def filter_items_valid_for_location(self, items, location_name):
    valid_items = []
    for item_name in items:
      if self.check_item_valid_in_location(item_name, location_name):
        valid_items.append(item_name)
    return valid_items
  
  def register_mutable_macros(self):
    self.mutable_macros: set[str] = set()
    #if entrances.EntranceRandomizer.is_enabled_by_options(self.options):
    if True: # temporarily_make_entrance_macros_impossible is used unconditionally at rando initialization
      for entrance_name in entrances.ZoneEntrance.all:
        self.mutable_macros.add("Can Access " + entrance_name)
      for zone_name in entrances.ZoneExit.all:
        self.mutable_macros.add("Can Access " + zone_name)
    if self.options.randomize_charts:
      for island in range(1, 49+1):
        self.mutable_macros.add(f"Chart for Island {island}")
    if self.options.required_bosses:
      self.mutable_macros.add("Can Defeat All Required Bosses")
      
  def set_macro(self, macro_name: str, req: LogicRequirement):
    if macro_name not in self.mutable_macros:
      raise ValueError(f"Attempting to update immutable macro {macro_name}")
    self.macros[macro_name] = req.specialize_for_seed(self)
  
  def update_entrance_connection_macros(self):
    # Update all the macros to take randomized entrances into account.
    for entrance_name, zone_name in self.rando.entrances.entrance_connections.items():
      zone_access_macro_name = "Can Access " + zone_name
      entrance_access_macro_name = "Can Access " + entrance_name
      self.set_macro(zone_access_macro_name, MacroReq(entrance_access_macro_name))
  
  def temporarily_make_dungeon_entrance_macros_impossible(self):
    # Update all the dungeon access macros to be considered "Impossible".
    # Useful when the item randomizer is deciding how to place keys in DRC.
    for zone_exit in entrances.DUNGEON_EXITS:
      dungeon_access_macro_name = "Can Access " + zone_exit.unique_name
      self.set_macro(dungeon_access_macro_name, Impossible)
  
  def temporarily_make_dungeon_entrance_macros_accessible(self):
    # Update all the dungeon access macros to be considered "Nothing".
    # Useful when the item randomizer is deciding how to place keys and the dungeons are nested.
    for zone_exit in entrances.DUNGEON_EXITS:
      dungeon_access_macro_name = "Can Access " + zone_exit.unique_name
      self.set_macro(dungeon_access_macro_name, Nothing)
  
  def temporarily_make_entrance_macros_impossible(self):
    # Update all the dungeon/secret cave access macros to be considered "Impossible".
    # Useful when the entrance randomizer is selecting which dungeons/secret caves should be allowed where.
    for entrance_name, zone_name in self.rando.entrances.entrance_connections.items():
      zone_access_macro_name = "Can Access " + zone_name
      self.set_macro(zone_access_macro_name, Impossible)
  
  def temporarily_make_entrance_macros_worst_case_scenario(self):
    # Update all the dungeon/secret cave access macros to be a combination of all the macros for
    # accessing dungeons/secret caves that can have their entrance randomized.
    for relevant_entrances, relevant_exits in self.rando.entrances.get_all_entrance_sets_to_be_randomized():
      self.temporarily_make_one_set_of_entrance_macros_worst_case_scenario(relevant_entrances, relevant_exits)
  
  def temporarily_make_one_set_of_entrance_macros_worst_case_scenario(self, relevant_entrances, relevant_exits):
    all_entrance_access_macros: set[MacroReq] = set()
    for entrance in relevant_entrances:
      entrance_access_macro_name = "Can Access " + entrance.entrance_name
      assert self.macros[entrance_access_macro_name] != Impossible
      all_entrance_access_macros.add(MacroReq(entrance_access_macro_name))
    can_access_all_entrances = And.from_iterable(all_entrance_access_macros)
    for zone_exit in relevant_exits:
      zone_access_macro_name = "Can Access " + zone_exit.unique_name
      self.set_macro(zone_access_macro_name, can_access_all_entrances)
  
  def update_chart_macros(self):
    # Update all the "Chart for Island" macros to take randomized charts into account.
    if not self.rando.charts.is_enabled():
      # Use default macros
      return

    for island_number in range(1, 49+1):
      chart_macro_name = "Chart for Island %d" % island_number
      chart_item_name = self.rando.charts.island_number_to_chart_name[island_number]
      
      if "Triforce Chart" in chart_item_name:
        req = And.from_elements(ItemReq(chart_item_name), MacroReq("Any Wallet Upgrade"))
      else:
        req = ItemReq(chart_item_name)
      
      self.set_macro(chart_macro_name, req)
  
  def update_required_bosses_macro(self):
    if not self.rando.boss_reqs.is_enabled():
      return
    required_boss_reqs = [
      OtherLocationReq(loc)
      for loc in self.rando.boss_reqs.required_boss_item_locations
    ]
    self.set_macro("Can Defeat All Required Bosses", And.from_iterable(required_boss_reqs))
  
  def temporarily_make_required_bosses_macro_worst_case_scenario(self):
    possible_boss_item_locations = [
      loc for loc in self.item_locations.keys()
      if "Boss" in self.item_locations[loc]["Types"]
    ]
    required_boss_reqs = [
      OtherLocationReq(loc)
      for loc in possible_boss_item_locations
    ]
    self.set_macro("Can Defeat All Required Bosses", And.from_iterable(required_boss_reqs))
  
  def clean_item_name(self, item_name):
    # Remove parentheses from any item names that may have them. (Formerly Master Swords, though that's not an issue anymore.)
    return item_name.replace("(", "").replace(")", "")
  
  def make_useless_progress_items_nonprogress(self):
    # Detect which progress items don't actually help access any locations with the user's current settings, and move
    # those over to the nonprogress item list instead.
    # This is so things like dungeons-only runs don't have a lot of useless items hogging the progress locations.
    
    if self.rando.entrances.is_enabled():
      # Since the randomizer hasn't decided which dungeon/secret cave will be where yet, we have to assume the worst
      # case scenario by considering that you need to be able to access all dungeon/secret cave entrances in order to
      # access each individual one.
      self.temporarily_make_entrance_macros_worst_case_scenario()
    
    if self.rando.boss_reqs.is_enabled():
      # Required bosses mode also hasn't decided on which bosses to make required, so assume the worst case here too.
      self.temporarily_make_required_bosses_macro_worst_case_scenario()
    
    filter_sunken_treasure = True
    if self.options.progression_triforce_charts or self.options.progression_treasure_charts:
      filter_sunken_treasure = False
    progress_locations = Logic.filter_locations_for_progression_static(
      list(self.item_locations.keys()),
      self.item_locations,
      self.options,
      filter_sunken_treasure=filter_sunken_treasure
    )
    
    items_needed = {}
    for location_name in progress_locations:
      requirement_expression = self.item_locations[location_name]["Need"]
      sub_items_needed = self.get_items_needed_by_req(requirement_expression)
      for item_name, num_required in sub_items_needed.items():
        items_needed[item_name] = max(num_required, items_needed.get(item_name, 0))
    sub_items_needed = self.get_items_needed_by_req(self.COMPLETE_GAME_REQ)
    for item_name, num_required in sub_items_needed.items():
      items_needed[item_name] = max(num_required, items_needed.get(item_name, 0))
    
    useful_items = self.flatten_items_needed_to_item_names(items_needed)
    
    all_progress_items_filtered = []
    for item_name in useful_items:
      if item_name == "Progressive Sword" and self.options.sword_mode == SwordMode.SWORDLESS:
        continue
      if self.is_dungeon_item(item_name) and not self.options.progression_dungeons:
        continue
      if item_name not in self.all_progress_items:
        if not (item_name.startswith("Triforce Chart ") or item_name.startswith("Treasure Chart")):
          raise Exception("Item %s opens up progress locations but is not in the list of all progress items." % item_name)
      all_progress_items_filtered.append(item_name)
    
    all_items_to_make_nonprogress = self.all_progress_items.copy()
    starting_items_to_remove = self.rando.starting_items.copy()
    for item_name in all_progress_items_filtered:
      if item_name not in all_items_to_make_nonprogress:
        if (item_name.startswith("Triforce Chart ") or item_name.startswith("Treasure Chart")):
          continue
      all_items_to_make_nonprogress.remove(item_name)
      if item_name in starting_items_to_remove:
        starting_items_to_remove.remove(item_name)
    unplaced_items_to_make_nonprogress = all_items_to_make_nonprogress.copy()
    for item_name in starting_items_to_remove:
      if item_name not in self.all_progress_items:
        continue
      unplaced_items_to_make_nonprogress.remove(item_name)
    
    for item_name in all_items_to_make_nonprogress:
      #print(item_name)
      if item_name.endswith(" Trap Chest"):
        # Don't remove traps from the progress items list even though they are useless.
        continue
      self.all_progress_items.remove(item_name)
      self.all_nonprogress_items.append(item_name)
    for item_name in unplaced_items_to_make_nonprogress:
      self.unplaced_progress_items.remove(item_name)
      self.unplaced_nonprogress_items.append(item_name)
    
    # Reset the macros if we changed them earlier.
    if self.rando.entrances.is_enabled():
      self.update_entrance_connection_macros()
    if self.rando.boss_reqs.is_enabled():
      self.update_required_bosses_macro()
  
  @staticmethod
  def split_location_name_by_zone(location_name: str) -> tuple[str, str]:
    if " - " in location_name:
      zone_name, specific_location_name = location_name.split(" - ", 1)
    else:
      zone_name = specific_location_name = location_name
    
    return zone_name, specific_location_name
  
  def is_dungeon_item(self, item_name):
    return (item_name in DUNGEON_PROGRESS_ITEMS or item_name in DUNGEON_NONPROGRESS_ITEMS)
  
  def is_dungeon_location(self, location_name, dungeon_name_to_match=None):
    zone_name, specific_location_name = self.split_location_name_by_zone(location_name)
    if zone_name not in self.DUNGEON_NAME_TO_SHORT_DUNGEON_NAME:
      # Not a dungeon.
      return False
    if dungeon_name_to_match and dungeon_name_to_match != zone_name:
      # Wrong dungeon.
      return False
    if "Sunken Treasure" in self.item_locations[location_name]["Types"]:
      # Outside the dungeon.
      return False
    return True
  
  def check_macro_met(self, macro: str) -> bool:
    return self.macros[macro].eval(self)

  def check_requirement_met(self, req: LogicRequirement):
    return req.eval(self)
  
  def check_location_accessible(self, location_name):
    return self.item_locations[location_name]["Need"].eval(self)
  
  def get_item_names_by_req(self, req: LogicRequirement):
    items_needed = self.get_items_needed_by_req(req)
    return self.flatten_items_needed_to_item_names(items_needed)

  def get_item_names_for_location(self, location_name: str):
    return self.get_item_names_by_req(self.item_locations[location_name]["Need"])
  
  def flatten_items_needed_to_item_names(self, items_needed: Mapping[str, int]):
    item_names = []
    for item_name, num_required in items_needed.items():
      item_names += [item_name]*num_required
    return item_names

  def get_items_needed_by_req(self, req: LogicRequirement) -> dict[str, int]:
    items_needed: dict[str, int] = {}
    subtree_reqs = recursive_children(req, macro_library=self.macros, ignore_cycles=True)
    for exp in subtree_reqs:
      if isinstance(exp, ItemReq):
        items_needed[exp.item] = max(items_needed.get(exp.item,0), exp.num)
      
    return items_needed
  
  def chart_name_for_location(self, location_name):
    reqs = self.get_items_needed_by_req(self.item_locations[location_name]["Need"])
    chart_name = [item_name for item_name in reqs if " Chart " in item_name]
    assert len(chart_name) == 1
    assert chart_name[0] in self.all_cleaned_item_names
    return chart_name[0]
  
  def filter_out_enemies_that_add_new_requirements(self, original_req: LogicRequirement, has_throwable_objects: bool, has_bomb_flowers: bool, possible_new_enemy_datas):
    # This function takes a list of enemy types and removes the ones that would add new required items for a room.
    # This is because the enemy randomizer cannot increase the logic requirements compared to when enemies are not randomized, it can only keep them the same or decrease them.
    
    # Accomplishing this by directly comparing the requirement lists for the original enemies in the room to the new possible enemies would be very complicated, if not impossible, to do accurately.
    # So instead, a brute-force approach is used.
    # The brute-force approach works like this:
    # * Build a list of progress items that were relevant for defeating the original enemies in the room.
    # * Build a very large list of all item combinations possible with the above items. This list is at least 2^n where n is the number of relevant items, but will be larger if having more than 1 of any given progressive item is relevant in this room. e.g. Hookshot being relevant multiplies the number of combos by 2 for having or not having it, but Fire & Ice Arrows multiplies the number of combos by 3 for having no bow, Hero's Bow, or Fire & Ice Arrows.
    # * Go through every single combination in this list and check if this combination allowed you to defeat all the original enemies in the room.
    # * For combinations that were valid for the original room, check to be sure that they are also valid for each enemy type we're considering placing in this room.
    # * Enemy types that cannot be beaten with even one item combination that could beat the original room are considered invalid and thrown away.
    
    # Default to assuming they're all allowed, remove ones as we find out they don't work.
    enemy_datas_allowed_here = possible_new_enemy_datas.copy()
    
    # Default to checking all enemy datas passed to this function.
    possible_new_enemy_datas_to_check = possible_new_enemy_datas.copy()
    
    # This tuple is the key we'll use into the cache to identify this set of requirement arguments.
    reqs_tuple_key = (original_req, has_throwable_objects, has_bomb_flowers)
    
    # However, we don't recheck ones that are already in the cache.
    if reqs_tuple_key not in self.cached_enemies_tested_for_reqs_tuple:
      self.cached_enemies_tested_for_reqs_tuple[reqs_tuple_key] = {}
    else:
      for possible_new_enemy_data in possible_new_enemy_datas:
        enemy_name = possible_new_enemy_data["Pretty name"]
        if enemy_name in self.cached_enemies_tested_for_reqs_tuple[reqs_tuple_key]:
          # Cached.
          possible_new_enemy_datas_to_check.remove(possible_new_enemy_data)
          if not self.cached_enemies_tested_for_reqs_tuple[reqs_tuple_key][enemy_name]:
            enemy_datas_allowed_here.remove(possible_new_enemy_data)
    
    if not possible_new_enemy_datas_to_check:
      # All the enemies we need to check have already been checked and cached. Return early to improve performance.
      return enemy_datas_allowed_here
    
    max_num_of_each_item_to_check = self.get_items_needed_by_req(original_req)
    
    # Remove starting items from being checked.
    for item_name, num_items in self.currently_owned_items.items():
      if item_name in max_num_of_each_item_to_check:
        max_num_of_each_item_to_check[item_name] -= num_items
        if max_num_of_each_item_to_check[item_name] <= 0:
          del max_num_of_each_item_to_check[item_name]
    
    if self.options.sword_mode == SwordMode.SWORDLESS:
      if "Progressive Sword" in max_num_of_each_item_to_check:
        del max_num_of_each_item_to_check["Progressive Sword"]
      if "Hurricane Spin" in max_num_of_each_item_to_check:
        del max_num_of_each_item_to_check["Hurricane Spin"]
    
    # print(f"{len(max_num_of_each_item_to_check)} relevant items")
    # num_combos_to_check = 1
    # for item_name, num in max_num_of_each_item_to_check.items():
    #   num_combos_to_check *= (num+1)
    # print(f"Checking up to {num_combos_to_check} item combos")
    # print(f"Combos to check: {num_combos_to_check} ({len(max_num_of_each_item_to_check)} items)")
    # if num_combos_to_check > 6144:
    #   raise Exception(f"Enemy randomizer got stuck in an exponential loop checking {num_combos_to_check} possibilities for requirement: {original_req_string!r}")
    
    biggest_combo = []
    for item_name, num in max_num_of_each_item_to_check.items():
      biggest_combo += [item_name]*num
    biggest_combo = tuple(biggest_combo)
    # print(f"Biggest item combo length: {len(biggest_combo)} items")
    # print(f"Biggest item combo: {biggest_combo}")
    
    item_combos_to_check, checked_combos = self.get_all_item_combo_subsets_meeting_req(biggest_combo, original_req)
    
    # print(f"Actually checking {len(item_combos_to_check)} combos")
    # print(f"Actually checking {len(item_combos_to_check)} combos (lengths: {', '.join(str(len(combo)) for combo in sorted(item_combos_to_check)[:30])})")
    # for combo in item_combos_to_check:
    #   print(combo)
    # print(f"Did a preliminary check on {len(checked_combos)} combos, will now fully check {len(item_combos_to_check)} combos")
    
    if len(item_combos_to_check) == 0:
      raise Exception("No item combos satisfied the requirement!")
    
    for item_combo in sorted(item_combos_to_check):
      with self.add_temporary_items(item_combo):
        # This check isn't necessary here as we already know all the combos returned from
        # get_all_item_combo_subsets_meeting_req must meet the req, so it's removed for efficiency.
        # if not self.check_logical_expression_req(orig_req_expression):
        #   continue
        
        for possible_new_enemy_data in possible_new_enemy_datas_to_check:
          if possible_new_enemy_data not in enemy_datas_allowed_here:
            # Already removed this one
            continue
          
          enemy_name = possible_new_enemy_data["Pretty name"]
          
          # TODO: Need to find a way to 100% guarantee the player has enough throwable objects to actually kill all the enemies.
          if has_throwable_objects and possible_new_enemy_data["Can be killed with thrown objects"]:
            # Allow enemies that can be killed by throwing stuff at them even if the player doesn't have the weapons to kill them.
            continue
          
          if has_bomb_flowers and possible_new_enemy_data["Can be killed with bomb flowers"]:
            # Allow enemies that can be killed by bombs in rooms with bomb flowers even if the player doesn't own the bombs upgrade.
            continue
          
          possible_new_enemy_req = possible_new_enemy_data["Requirements to defeat"]
          new_req_met = self.check_requirement_met(possible_new_enemy_req)
          if not new_req_met:
            enemy_datas_allowed_here.remove(possible_new_enemy_data)
            self.cached_enemies_tested_for_reqs_tuple[reqs_tuple_key][enemy_name] = False
    
    for enemy_data in enemy_datas_allowed_here:
      enemy_name = enemy_data["Pretty name"]
      self.cached_enemies_tested_for_reqs_tuple[reqs_tuple_key][enemy_name] = True
    
    return enemy_datas_allowed_here
  
  def get_all_item_combo_subsets_meeting_req(self, item_combo: tuple, orig_req: LogicRequirement) -> tuple[set, set]:
    # This function returns all subsets of an item combo that meet a particular requirement.
    # e.g. If the requirement is 'Hookshot', and the initial combo is ('Hookshot', 'Deku Leaf'),
    # then this function would return {('Hookshot', 'Deku Leaf'), ('Hookshot')} as both of those
    # combos satisfy the requirement of 'Hookshot'.
    # e.g. If the requirement is 'Nothing' and the initial combo is ('DRC Small Key', 'Bombs'), then
    # this function would return {('DRC Small Key', 'Bombs'), ('DRC Small Key'), ('Bombs'), ()},
    # as all of those satisfy the requirement of 'Nothing'.
    # If this function finds a combo that does not satisfy the requirements, it will exit early and
    # not check any subsets of that combo. This allows the function to usually be fast, even though
    # the worst case time complexity is exponential with the number of items in the combo.
    
    matched_combos = set()
    checked_combos = set()
    self.get_all_item_combo_subsets_meeting_req_recursive(
      item_combo, orig_req,
      matched_combos, checked_combos,
    )
    return matched_combos, checked_combos
  
  def get_all_item_combo_subsets_meeting_req_recursive(self, item_combo: tuple, orig_req: LogicRequirement, matched_combos: set, checked_combos: set):
    if item_combo in checked_combos:
      return
    
    with self.add_temporary_items(item_combo):
      orig_req_met = self.check_requirement_met(orig_req)
    
    checked_combos.add(item_combo)
    # if len(checked_combos) > 1000 and len(checked_combos) % 10000 == 0:
    #   print(f"Did a preliminary check on {len(checked_combos)} combos so far...")
    if len(checked_combos) >= 10000:
      raise Exception(f"Enemy randomizer got stuck in an exponential loop checking over {len(checked_combos)} possibilities for requirement: {orig_req!r}")
    
    if not orig_req_met:
      return
    matched_combos.add(item_combo)
    
    for item in item_combo:
      # Recursively check all subsets by removing one item at a time.
      # Note that because item_combo can have duplicate items in it, this loop gets run more times
      # than necessary. But this is okay as the duplicates will be immediately caught in the next
      # call down due to checked_combos anyway. If we tried to optimize the duplicates out here too
      # it would actually make it slower.
      subset_item_combo = list(item_combo)
      subset_item_combo.remove(item)
      subset_item_combo = tuple(subset_item_combo)
      self.get_all_item_combo_subsets_meeting_req_recursive(
        subset_item_combo, orig_req,
        matched_combos, checked_combos,
      )

  def compile_macros(self, macros: dict[str, LogicRequirement]):
    self.macros = {}
    self.macros = {name: macros[name].specialize_for_seed(self) for name in self.mutable_macros}

    undone_macros = set(macros.keys())
    new_terminals = self.mutable_macros.copy()
    while new_terminals:
      undone_macros -= new_terminals
      new_terminals = set()
      for name in undone_macros:
        macros[name] = macros[name].specialize_for_seed(self)
        if expr_is_terminal(macros[name], terminal_macros=self.macros, macro_library=macros):
          new_terminals.add(name)
          self.macros[name] = macros[name]
    if undone_macros:
      raise Exception(f"Unable to reduce all macros. Remaining: {undone_macros}")