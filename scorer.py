"""
scorer.py — Automatic scoring system for Risiko AI agents.

Scores each AI player based on observable game state metrics and generates
natural-language coaching feedback that is injected into the next turn's
CrewAI task prompt, creating a continuous self-improving feedback loop.
"""
from typing import Dict, Optional, Tuple
import map as game_map


class TurnScore:
    """Holds the full breakdown of a player's score for one turn snapshot."""
    def __init__(
        self,
        total: float,
        territory_score: float,
        continent_score: float,
        army_score: float,
        card_score: float,
        frontier_pressure: float,
        territories_count: int,
        total_units: int,
        continents_held: int,
        cards_count: int,
    ):
        self.total = total
        self.territory_score = territory_score
        self.continent_score = continent_score
        self.army_score = army_score
        self.card_score = card_score
        self.frontier_pressure = frontier_pressure
        self.territories_count = territories_count
        self.total_units = total_units
        self.continents_held = continents_held
        self.cards_count = cards_count

    def to_dict(self) -> Dict:
        return {
            "total": round(self.total, 2),
            "territory_score": round(self.territory_score, 2),
            "continent_score": round(self.continent_score, 2),
            "army_score": round(self.army_score, 2),
            "card_score": round(self.card_score, 2),
            "frontier_pressure": round(self.frontier_pressure, 2),
            "territories_count": self.territories_count,
            "total_units": self.total_units,
            "continents_held": self.continents_held,
            "cards_count": self.cards_count,
        }


class GameScorer:
    """
    Scores a player based on their current game state.

    Scoring breakdown (max ~100 pts):
      - Territory control  : 0–35 pts  (share of total territories)
      - Continent control  : 0–30 pts  (continent bonuses × weight)
      - Army strength      : 0–20 pts  (total units, capped)
      - Card potential     : 0–10 pts  (cards held × 2)
      - Frontier pressure  : 0–5  pts  (bonus for units on contested borders)
    """

    def score_player(self, game, player) -> TurnScore:
        from game_logic import GameManager, Player  # local import to avoid circular
        total_territories = max(1, len(game.territories))
        player_territories = [t for t in game.territories.values() if t.owner == player]
        player_t_names = {t.name for t in player_territories}

        # --- Territory score (0–35) ---
        territory_score = (len(player_territories) / total_territories) * 35

        # --- Continent score (0–30) ---
        continent_score = 0.0
        continents_held = 0
        for continent, members in game_map.continents.items():
            if all(m in player_t_names for m in members):
                bonus = game_map.continentsBonus.get(continent, 0)
                continent_score += bonus * 3  # weight continents highly
                continents_held += 1
        continent_score = min(30.0, continent_score)

        # --- Army strength (0–20) ---
        total_units = sum(t.units for t in player_territories)
        army_score = min(20.0, total_units * 0.4)

        # --- Card potential (0–10) ---
        cards_count = len(player.cards)
        card_score = min(10.0, cards_count * 2.0)

        # --- Frontier pressure bonus (0–5) ---
        # Reward players who mass units on contested frontiers
        frontier_units = 0
        for t in player_territories:
            neighbors = game_map.adjacency.get(t.name, [])
            is_frontier = any(
                game.territories[n].owner != player
                for n in neighbors
                if n in game.territories
            )
            if is_frontier:
                frontier_units += t.units
        avg_frontier = frontier_units / max(1, len(player_territories))
        frontier_pressure = min(5.0, avg_frontier * 0.5)

        total = territory_score + continent_score + army_score + card_score + frontier_pressure

        return TurnScore(
            total=total,
            territory_score=territory_score,
            continent_score=continent_score,
            army_score=army_score,
            card_score=card_score,
            frontier_pressure=frontier_pressure,
            territories_count=len(player_territories),
            total_units=total_units,
            continents_held=continents_held,
            cards_count=cards_count,
        )

    def generate_feedback(self, current: TurnScore, previous: Optional[TurnScore]) -> str:
        """
        Produces a concise coaching message comparing current vs previous score.
        This text is injected into the agent's next task prompt.
        """
        lines = []

        if previous is not None:
            delta = current.total - previous.total
            t_delta = current.territories_count - previous.territories_count
            u_delta = current.total_units - previous.total_units

            # Overall verdict
            if delta >= 10:
                lines.append(f"★★★ OUTSTANDING turn — score +{delta:.1f} pts.")
            elif delta >= 4:
                lines.append(f"★★  GOOD turn — score +{delta:.1f} pts.")
            elif delta >= 0:
                lines.append(f"★   STEADY turn — score +{delta:.1f} pts.")
            elif delta >= -5:
                lines.append(f"⚠   WEAK turn — score {delta:.1f} pts.")
            else:
                lines.append(f"✗   POOR turn — score {delta:.1f} pts. Reassess strategy.")

            # Territory delta
            if t_delta > 0:
                lines.append(f"  Territories: +{t_delta} conquered (good expansion).")
            elif t_delta < 0:
                lines.append(f"  Territories: {t_delta} lost (defend your flanks).")
            else:
                lines.append(f"  Territories: unchanged.")

            # Army delta
            if u_delta > 2:
                lines.append(f"  Army grew by {u_delta} units.")
            elif u_delta < -2:
                lines.append(f"  Army shrank by {abs(u_delta)} units — avoid wasteful attacks.")

            # Continent tip
            if current.continents_held > previous.continents_held:
                lines.append(f"  Continent bonus secured! ({current.continents_held} continent(s) held).")
            elif current.continent_score == 0 and current.territories_count > 5:
                lines.append("  PRIORITY: Focus on completing a continent for the bonus income.")
        else:
            lines.append("First turn — no baseline yet. Establish a strong opening position.")

        # Absolute snapshot
        lines.append(
            f"Score: {current.total:.1f}/100 "
            f"[T:{current.territory_score:.0f} C:{current.continent_score:.0f} "
            f"A:{current.army_score:.0f} K:{current.card_score:.0f} F:{current.frontier_pressure:.0f}]"
        )

        return " ".join(lines)
