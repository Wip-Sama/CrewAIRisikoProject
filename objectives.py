import random
from typing import List, Dict, Optional

class Objective:
    def __init__(self, description: str, objective_type: str, target_continents: List[str] = None, target_count: int = 0, target_min_units: int = 0, target_color: str = None):
        self.description = description
        self.type = objective_type # 'continent', 'territory', 'elimination'
        self.target_continents = target_continents or []
        self.target_count = target_count
        self.target_min_units = target_min_units
        self.target_color = target_color

    def to_dict(self):
        return {
            "description": self.description,
            "type": self.type
        }

def get_objective_templates() -> List[Objective]:
    return [
        # Continent Objectives
        Objective("Conquistare la totalità del Nord America e dell'Africa.", "continent", ["America del Nord", "Africa"]),
        Objective("Conquistare la totalità del Nord America e dell'Oceania.", "continent", ["America del Nord", "Oceania"]),
        Objective("Conquistare la totalità dell'Asia e del Sud America.", "continent", ["Asia", "America del Sud"]),
        Objective("Conquistare la totalità dell'Asia e dell'Africa.", "continent", ["Asia", "Africa"]),
        Objective("Conquistare la totalità di Europa, Sud America e un terzo continente a scelta.", "continent", ["Europa", "America del Sud"], target_count=3),
        Objective("Conquistare la totalità di Europa, Oceania e un terzo continente a scelta.", "continent", ["Europa", "Oceania"], target_count=3),
        
        # Territorial Presence
        Objective("Conquistare 24 territori a scelta sulla mappa.", "territory", target_count=24),
        Objective("Occupare 18 territori, ognuno dei quali deve essere presidiato da almeno due armate.", "territory", target_count=18, target_min_units=2),
        
        # Elimination (will be specialized per game)
        # Black, Red, Yellow, Green, Blue, Purple
    ]

def assign_objectives(players: List, colors: Dict[str, str]):
    templates = get_objective_templates()
    
    # Add elimination objectives for each color present in game
    for color_name, color_hex in colors.items():
        templates.append(Objective(f"Distruggi le armate {color_name}.", "elimination", target_color=color_hex))
    
    random.shuffle(templates)
    
    assigned = []
    for player in players:
        obj = templates.pop()
        
        # Check if elimination objective is valid for this player
        if obj.type == "elimination":
            # If target color is player's own color, or target color not in game, fallback to 24 territories
            # Note: colors dict contains all possible colors, but we should only care about colors active in game
            active_colors = [p.color for p in players]
            if obj.target_color == player.color or obj.target_color not in active_colors:
                obj = Objective("Conquistare 24 territori a scelta sulla mappa (Obiettivo di ripiego).", "territory", target_count=24)
        
        player.objective = obj
