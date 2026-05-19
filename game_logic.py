import random
from typing import Dict, List, Optional, Tuple
from data import GamePhase, UnitType
import map as game_map
import objectives

class Player:
    def __init__(self, name: str, color: str, is_ai: bool = False):
        self.name = name
        self.color = color
        self.is_ai = is_ai
        self.cards: List[str] = [] # Territory names (or 'JOLLY')
        self.territories_count = 0
        self.objective = None
        self.initial_reinforcements_left = 0

class Territory:
    def __init__(self, name: str, image_id: str, territory_type: UnitType):
        self.name = name
        self.image_id = image_id
        self.type = territory_type
        self.owner: Optional[Player] = None
        self.units = 0

    @property
    def adjacent(self) -> List[str]:
        return game_map.adjacency.get(self.name, [])

class GameManager:
    def __init__(self, player_names: List[str]):
        colors = {
            "Rossa": "#EF4444",
            "Blu": "#3B82F6",
            "Verde": "#10B981",
            "Gialla": "#F59E0B",
            "Viola": "#8B5CF6",
            "Nera": "#1F2937"
        }
        color_list = list(colors.values())
        self.players = [Player(name, color_list[i % len(color_list)]) for i, name in enumerate(player_names)]
        self.current_player_index = 0
        self.phase = GamePhase.INITIAL_PLACEMENT
        self.territories: Dict[str, Territory] = {}
        self.last_dice_roll: Optional[Dict] = None
        self.reinforcements_to_place = 0
        self.initial_placements_count = 0 # To track 3 units per turn
        self.conquered_this_turn = False
        self.battle_log: List[str] = ["[System] Simulation initialized."]
        self.last_acted_territory: Optional[str] = None
        self.winner: Optional[Player] = None
        self.win_reason: str = ""
        
        self._initialize_territories()
        self._initialize_deck()
        self._assign_initial_territories()
        self._assign_objectives(colors)
        self._calculate_reinforcements() # For standard loop setup
        self._calculate_initial_reinforcements()

    def add_log(self, message: str):
        self.battle_log.append(message)
        # Keep log size reasonable but history rich
        if len(self.battle_log) > 200:
            self.battle_log.pop(1) # Keep initialization message

    def _initialize_deck(self):
        self.deck = list(self.territories.keys())
        self.deck.append("JOLLY_1")
        self.deck.append("JOLLY_2")
        random.shuffle(self.deck)

    def draw_card(self, player: Player):
        if self.deck:
            card = self.deck.pop(0)
            player.cards.append(card)
            msg = f"{player.name} drew card: {card}"
            print(f"[GAME] {msg}")
            self.add_log(msg)
            return card
        return None

    def _assign_objectives(self, colors: Dict[str, str]):
        objectives.assign_objectives(self.players, colors)

    def _calculate_initial_reinforcements(self):
        # Standard Risk initial armies based on player count
        counts = {2: 40, 3: 35, 4: 30, 5: 25, 6: 20}
        total_armies = counts.get(len(self.players), 20)
        
        for p in self.players:
            p.initial_reinforcements_left = total_armies - p.territories_count
        
        self.reinforcements_to_place = 3 # Start with 3 for the first turn of INITIAL_PLACEMENT

    def _get_card_type(self, card_name: str) -> UnitType:
        if "JOLLY" in card_name:
            return UnitType.JOLLY
        return game_map.cardType.get(card_name, UnitType.FANTE)

    def calculate_predicted_reinforcements(self, player: Player) -> int:
        # Standard: Territories / 3, minimum 3
        count = max(3, player.territories_count // 3)
        
        # Continent bonuses
        player_territories = [t.name for t in self.territories.values() if t.owner == player]
        for continent, members in game_map.continents.items():
            if all(m in player_territories for m in members):
                count += game_map.continentsBonus[continent]
        
        # Add best possible card set
        best_set_bonus = self._get_best_set_bonus(player)
        count += best_set_bonus
        
        return count

    def _get_best_set_bonus(self, player: Player) -> int:
        # This is now used only for display/prediction
        if len(player.cards) < 3:
            return 0
            
        card_types = [self._get_card_type(c) for c in player.cards]
        # Simplified prediction: count how many sets could be made
        # For now, let's keep the single best as a "Potential" indicator
        # but the user requested multiple sets can be used.
        # Let's just return the sum of all possible sets for the prediction.
        return self._calculate_all_possible_bonuses(card_types)

    def _calculate_all_possible_bonuses(self, card_types: List[UnitType]) -> int:
        types_count = {
            UnitType.FANTE: card_types.count(UnitType.FANTE),
            UnitType.CAVALLO: card_types.count(UnitType.CAVALLO),
            UnitType.CANNONE: card_types.count(UnitType.CANNONE),
            UnitType.JOLLY: card_types.count(UnitType.JOLLY)
        }
        
        total_bonus = 0
        working_counts = types_count.copy()
        
        # Greedy check for sets (this is just for prediction)
        while True:
            added = False
            # Jolly + 2 of same
            if working_counts[UnitType.JOLLY] >= 1:
                for t in [UnitType.FANTE, UnitType.CAVALLO, UnitType.CANNONE]:
                    if working_counts[t] >= 2:
                        total_bonus += 12
                        working_counts[UnitType.JOLLY] -= 1
                        working_counts[t] -= 2
                        added = True
                        break
            if added: continue
            
            # 1 of each
            if working_counts[UnitType.FANTE] >= 1 and working_counts[UnitType.CAVALLO] >= 1 and working_counts[UnitType.CANNONE] >= 1:
                total_bonus += 10
                working_counts[UnitType.FANTE] -= 1
                working_counts[UnitType.CAVALLO] -= 1
                working_counts[UnitType.CANNONE] -= 1
                added = True
                continue
                
            # 3 of same
            for t in [UnitType.FANTE, UnitType.CAVALLO, UnitType.CANNONE]:
                if working_counts[t] >= 3:
                    total_bonus += 8
                    working_counts[t] -= 3
                    added = True
                    break
            if not added: break
            
        return total_bonus

    def get_tradeable_set(self, player: Player) -> Optional[List[str]]:
        """Returns the best tradeable set of 3 cards for a player, or None if no valid set exists."""
        if len(player.cards) < 3:
            return None

        cards = player.cards
        card_types = {c: self._get_card_type(c) for c in cards}
        jolly_cards = [c for c in cards if card_types[c] == UnitType.JOLLY]
        non_jolly = [c for c in cards if card_types[c] != UnitType.JOLLY]

        # Try Jolly + 2 of same type (highest bonus = 12)
        for jolly in jolly_cards:
            for unit_type in [UnitType.FANTE, UnitType.CAVALLO, UnitType.CANNONE]:
                same = [c for c in non_jolly if card_types[c] == unit_type]
                if len(same) >= 2:
                    return [jolly, same[0], same[1]]

        # Try 1 of each type (bonus = 10)
        fante = [c for c in non_jolly if card_types[c] == UnitType.FANTE]
        cavallo = [c for c in non_jolly if card_types[c] == UnitType.CAVALLO]
        cannone = [c for c in non_jolly if card_types[c] == UnitType.CANNONE]
        if fante and cavallo and cannone:
            return [fante[0], cavallo[0], cannone[0]]

        # Try 3 of same type (bonus = 8)
        for unit_type in [UnitType.FANTE, UnitType.CAVALLO, UnitType.CANNONE]:
            same = [c for c in non_jolly if card_types[c] == unit_type]
            if len(same) >= 3:
                return [same[0], same[1], same[2]]

        return None

    def trade_cards(self, card_names: List[str]) -> bool:
        if self.phase != GamePhase.PLACE_ARMIES:
            return False
            
        player = self.get_current_player()
        if not all(c in player.cards for c in card_names):
            return False
            
        if len(card_names) != 3:
            return False
            
        card_types = [self._get_card_type(c) for c in card_names]
        types_count = {
            UnitType.FANTE: card_types.count(UnitType.FANTE),
            UnitType.CAVALLO: card_types.count(UnitType.CAVALLO),
            UnitType.CANNONE: card_types.count(UnitType.CANNONE),
            UnitType.JOLLY: card_types.count(UnitType.JOLLY)
        }
        
        bonus = 0
        if types_count[UnitType.JOLLY] == 1:
            if any(types_count[t] == 2 for t in [UnitType.FANTE, UnitType.CAVALLO, UnitType.CANNONE]):
                bonus = 12
        elif all(types_count[t] == 1 for t in [UnitType.FANTE, UnitType.CAVALLO, UnitType.CANNONE]):
            bonus = 10
        elif any(types_count[t] == 3 for t in [UnitType.FANTE, UnitType.CAVALLO, UnitType.CANNONE]):
            bonus = 8
            
        if bonus > 0:
            self.reinforcements_to_place += bonus
            for c in card_names:
                player.cards.remove(c)
                if "JOLLY" not in c:
                    self.deck.append(c)
            random.shuffle(self.deck)
            return True
            
        return False

    def _initialize_territories(self):
        for name, image_id in game_map.territoryImageMapping.items():
            t_type = game_map.cardType.get(name, UnitType.FANTE)
            self.territories[name] = Territory(name, image_id, t_type)

    def _assign_initial_territories(self):
        t_names = list(self.territories.keys())
        random.shuffle(t_names)
        
        for i, name in enumerate(t_names):
            player = self.players[i % len(self.players)]
            self.territories[name].owner = player
            self.territories[name].units = 1 # Start with 1 unit
            player.territories_count += 1

    def _calculate_reinforcements(self):
        player = self.get_current_player()
        # Standard: Territories / 3, minimum 0
        count = max(0, player.territories_count // 3)
        
        # Continent bonuses
        player_territories = [t.name for t in self.territories.values() if t.owner == player]
        for continent, members in game_map.continents.items():
            if all(m in player_territories for m in members):
                count += game_map.continentsBonus[continent]
                
        self.reinforcements_to_place = count

    def check_winner(self) -> bool:
        # Check if current player met their objective
        player = self.get_current_player()
        if not player.objective:
            return False

        obj = player.objective
        met = False

        if obj.type == "continent":
            player_territories = [t.name for t in self.territories.values() if t.owner == player]
            
            # 1. Check if all REQUIRED continents are owned
            all_required_owned = True
            for continent in obj.target_continents:
                members = game_map.continents.get(continent, [])
                if not all(m in player_territories for m in members):
                    all_required_owned = False
                    break
            
            if all_required_owned:
                # 2. If target_count > required, count how many ADDITIONAL continents are owned
                if obj.target_count > len(obj.target_continents):
                    continents_owned = len(obj.target_continents)
                    for continent, members in game_map.continents.items():
                        if continent not in obj.target_continents:
                            if all(m in player_territories for m in members):
                                continents_owned += 1
                    
                    if continents_owned >= obj.target_count:
                        met = True
                else:
                    # No choice continents needed, just the required ones
                    met = True

        elif obj.type == "territory":
            if player.territories_count >= obj.target_count:
                if obj.target_min_units > 0:
                    qualifying_territories = sum(1 for t in self.territories.values() if t.owner == player and t.units >= obj.target_min_units)
                    if qualifying_territories >= obj.target_count:
                        met = True
                else:
                    met = True

        elif obj.type == "elimination":
            # Check if target color player has 0 territories
            target_player = next((p for p in self.players if p.color == obj.target_color), None)
            if target_player and target_player.territories_count == 0:
                met = True

        if met:
            self.winner = player
            self.win_reason = obj.description
            self.phase = GamePhase.ENDGAME
            self.add_log(f"GAME OVER! {player.name} won. Reason: {obj.description}")
            return True
        return False

    def get_current_player(self) -> Player:
        return self.players[self.current_player_index]

    def is_human_turn(self) -> bool:
        return not self.get_current_player().is_ai

    def next_phase(self):
        if self.phase == GamePhase.INITIAL_PLACEMENT:
            # Check if anyone has reinforcements left
            if any(p.initial_reinforcements_left > 0 for p in self.players):
                return False # Still in initial placement
            self.phase = GamePhase.PLACE_ARMIES
            self.current_player_index = 0
            self.add_log(f"Phase changed to PLACE ARMIES. Turn: {self.get_current_player().name}")
            self._calculate_reinforcements()
            return True

        if self.phase == GamePhase.PLACE_ARMIES:
            if self.reinforcements_to_place > 0:
                return False # Must place all reinforcements
            self.phase = GamePhase.BATTLE
            self.add_log(f"Phase changed to BATTLE")
        elif self.phase == GamePhase.BATTLE:
            self.phase = GamePhase.MOVE
            self.add_log(f"Phase changed to MOVE")
        elif self.phase == GamePhase.MOVE:
            if self.conquered_this_turn:
                self.draw_card(self.get_current_player())
            
            # Reset flag and move to next player
            self.conquered_this_turn = False
            if self.check_winner():
                return True
            self.current_player_index = (self.current_player_index + 1) % len(self.players)
            self.phase = GamePhase.PLACE_ARMIES
            self.add_log(f"--- Turn End. Next: {self.get_current_player().name} ---")
            self._calculate_reinforcements()
        return True

    def place_armies(self, territory_name: str, count: int) -> bool:
        player = self.get_current_player()
        territory = self.territories.get(territory_name)
        if not territory or territory.owner != player:
            return False

        if self.phase == GamePhase.INITIAL_PLACEMENT:
            if count > self.reinforcements_to_place or count > player.initial_reinforcements_left:
                return False
            
            territory.units += count
            player.initial_reinforcements_left -= count
            self.reinforcements_to_place -= count
            self.initial_placements_count += count

            # If player finished their 3 units OR they are out of units entirely
            if self.initial_placements_count >= 3 or player.initial_reinforcements_left == 0:
                self.current_player_index = (self.current_player_index + 1) % len(self.players)
                self.initial_placements_count = 0
                
                # Check if we should switch phase
                if all(p.initial_reinforcements_left == 0 for p in self.players):
                    self.next_phase()
                else:
                    # Skip players who have no reinforcements left
                    while self.players[self.current_player_index].initial_reinforcements_left == 0:
                        self.current_player_index = (self.current_player_index + 1) % len(self.players)
                    
                    # Set reinforcements for next player
                    next_player = self.get_current_player()
                    self.reinforcements_to_place = min(3, next_player.initial_reinforcements_left)
            return True

        if self.phase != GamePhase.PLACE_ARMIES:
            return False
        
        if count > self.reinforcements_to_place:
            return False
        
        territory.units += count
        self.reinforcements_to_place -= count
        self.last_acted_territory = territory_name
        self.add_log(f"{player.name} deployed {count} units to {territory_name}")
        return True

    def attack(self, attacker_name: str, defender_name: str, attacker_count: int) -> Optional[Dict]:
        """Attack with `attacker_count` total units. Dice are capped at 3 per standard rules.
        On conquest, all surviving committed units move into the territory."""
        if self.phase != GamePhase.BATTLE:
            return None
        
        att_t = self.territories.get(attacker_name)
        def_t = self.territories.get(defender_name)
        
        if not att_t or not def_t or att_t.owner != self.get_current_player() or def_t.owner == self.get_current_player():
            return None
        
        # Must have units to attack
        if att_t.units <= 1:
            return None
        
        # Must be adjacent
        if defender_name not in game_map.adjacency.get(attacker_name, []):
            return None
        
        # Clamp committed units to what is actually available (must leave at least 1 behind)
        attacker_count = min(attacker_count, att_t.units - 1)
        attacker_count = max(1, attacker_count)

        # Dice are always capped at 3 per standard Risk rules
        attacker_dice = min(attacker_count, 3)
        defender_dice = min(def_t.units, 3)
        
        att_rolls = sorted([random.randint(1, 6) for _ in range(attacker_dice)], reverse=True)
        def_rolls = sorted([random.randint(1, 6) for _ in range(defender_dice)], reverse=True)
        
        att_losses = 0
        def_losses = 0
        
        for a, d in zip(att_rolls, def_rolls):
            if a > d:
                def_losses += 1
            else:
                att_losses += 1
                
        att_t.units -= att_losses
        def_t.units -= def_losses
        
        conquered = False
        if def_t.units <= 0:
            conquered = True
            self.conquered_this_turn = True
            old_owner = def_t.owner
            old_owner.territories_count -= 1
            
            def_t.owner = self.get_current_player()
            def_t.owner.territories_count += 1
            
            # Move ALL committed units (minus dice losses) into the conquered territory
            surviving_committed = attacker_count - att_losses
            surviving_committed = max(1, surviving_committed)  # Ensure at least 1 moves in
            # Ensure the source still keeps at least 1 unit
            surviving_committed = min(surviving_committed, att_t.units - 1)
            def_t.units = surviving_committed
            att_t.units -= surviving_committed

            # If old_owner is now fully eliminated, check elimination objectives
            if old_owner.territories_count == 0:
                attacker = self.get_current_player()
                self.add_log(f"{old_owner.name} has been ELIMINATED by {attacker.name}!")
                for p in self.players:
                    if p == old_owner:
                        continue
                    if p.objective and p.objective.type == "elimination" and p.objective.target_color == old_owner.color:
                        if p != attacker:
                            # This player wanted to eliminate old_owner but someone else did it
                            # Convert their objective to the fallback: 24 territories
                            import objectives as obj_module
                            p.objective = obj_module.Objective(
                                "Conquistare 24 territori a scelta sulla mappa (Obiettivo di ripiego).",
                                "territory",
                                target_count=24
                            )
                            self.add_log(f"{p.name}'s elimination objective failed — converted to 24 territories.")
            
        result = {
            "attacker_rolls": att_rolls,
            "defender_rolls": def_rolls,
            "attacker_losses": att_losses,
            "defender_losses": def_losses,
            "conquered": conquered
        }
        self.last_dice_roll = result
        self.last_acted_territory = defender_name
        self.add_log(f"{self.get_current_player().name} attacked {defender_name} from {attacker_name} ({att_losses}L vs {def_losses}L)")
        if conquered:
            self.add_log(f"{defender_name} CONQUERED by {self.get_current_player().name}!")
        return result

    def fortify(self, from_t_name: str, to_t_name: str, count: int) -> bool:
        if self.phase != GamePhase.MOVE:
            return False
            
        f_t = self.territories.get(from_t_name)
        t_t = self.territories.get(to_t_name)
        
        if not f_t or not t_t or f_t.owner != self.get_current_player() or t_t.owner != self.get_current_player():
            return False
            
        if f_t.units <= count:
            return False
            
        # Check adjacency (optional but good)
        if to_t_name not in game_map.adjacency.get(from_t_name, []):
            return False
            
        f_t.units -= count
        t_t.units += count
        self.last_acted_territory = to_t_name
        self.add_log(f"{self.get_current_player().name} moved {count} units from {from_t_name} to {to_t_name}")
        
        # Fortify typically ends the move phase
        self.next_phase()
        return True

    def get_state(self) -> Dict:
        return {
            "phase": self.phase.name,
            "current_player": self.get_current_player().name,
            "winner": self.winner.name if self.winner else None,
            "win_reason": self.win_reason,
            "reinforcements": self.reinforcements_to_place,
            "last_dice_roll": self.last_dice_roll,
            "last_acted_territory": self.last_acted_territory,
            "battle_log": self.battle_log,
            "territories": {
                name: {
                    "name": t.name,
                    "owner": t.owner.name if t.owner else "Neutral",
                    "owner_color": t.owner.color if t.owner else "#9CA3AF",
                    "units": t.units,
                    "type": t.type.name,
                    "image_id": t.image_id,
                    "adjacent": game_map.adjacency.get(t.name, [])
                } for name, t in self.territories.items()
            },
            "players": [
                {
                    "name": p.name,
                    "color": p.color,
                    "is_ai": p.is_ai,
                    "territories": p.territories_count,
                    "objective": p.objective.to_dict() if p.objective else None,
                    "initial_left": p.initial_reinforcements_left,
                    "cards": [
                        {"name": c, "type": self._get_card_type(c).name} for c in p.cards
                    ],
                    "predicted_reinforcements": self.calculate_predicted_reinforcements(p),
                    "conquered_continents": [
                        {"name": name, "bonus": game_map.continentsBonus[name]}
                        for name, members in game_map.continents.items()
                        if all(self.territories[m].owner == p for m in members)
                    ]
                } for p in self.players
            ]
        }

    def get_player_state(self, player_name: str) -> Dict:
        """Returns the game state from the perspective of a specific player (hiding enemy cards and objectives).
        This is prepared specifically to feed into LLM/CrewAI agents."""
        state = self.get_state()
        
        # Filter player specific sensitive info
        for p_data in state["players"]:
            if p_data["name"] != player_name:
                p_data["objective"] = None
                # Instead of giving the exact cards, just give the count of cards the enemy has
                p_data["cards"] = len(p_data["cards"])
                
        return state
