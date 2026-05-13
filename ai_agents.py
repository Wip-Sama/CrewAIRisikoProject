import os
import random
from dotenv import load_dotenv
load_dotenv()
import threading
import time
import uuid
from typing import Dict, List, Optional
from game_logic import GameManager, GamePhase
from data import UnitType
from scorer import GameScorer, TurnScore

from crewai import Agent, Task, Crew, Process
from langchain_core.tools import StructuredTool
import json
import logging

logging.getLogger("crewai").setLevel(logging.WARNING)

# Directory where score history is persisted
TRAINING_DIR = os.path.join(os.path.dirname(__file__), "training_data")
os.makedirs(TRAINING_DIR, exist_ok=True)

_scorer = GameScorer()

# LLM Configuration
def get_llm():
    """
    Returns a configured LangChain ChatModel based on .env settings.
    """
    provider = os.getenv("MODEL_PROVIDER", "openai").lower()
    try:
        if provider == "openai":
            from langchain_openai import ChatOpenAI
            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                print("[Warning] OPENAI_API_KEY not found in .env")
            return ChatOpenAI(model=os.getenv("OPENAI_MODEL_NAME", "gpt-4o"), api_key=api_key)
        elif provider == "google":
            from langchain_google_genai import ChatGoogleGenerativeAI
            api_key = os.getenv("GOOGLE_API_KEY")
            if not api_key:
                print("[Warning] GOOGLE_API_KEY not found in .env")
            return ChatGoogleGenerativeAI(
                model=os.getenv("GOOGLE_MODEL_NAME", "gemini-1.5-pro"),
                google_api_key=api_key
            )
        elif provider == "groq":
            from langchain_groq import ChatGroq
            api_key = os.getenv("GROQ_API_KEY")
            if not api_key:
                print("[Warning] GROQ_API_KEY not found in .env")
            return ChatGroq(model=os.getenv("GROQ_MODEL_NAME", "llama3-70b-8192"), groq_api_key=api_key)
    except Exception as e:
        print(f"[LLM Error] Failed to initialize {provider} provider: {e}")
    return None


class BaseAgent:
    def __init__(self, name: str):
        self.name = name

    def execute_turn(self, game: GameManager):
        current_p_name = game.get_current_player().name
        max_actions = 30
        actions_taken = 0

        if game.get_current_player().is_ai:
            print(f"[AI] {self.name} starting turn. Phase: {game.phase.name}")

        while game.get_current_player().name == current_p_name and actions_taken < max_actions:
            actions_taken += 1
            try:
                if game.phase == GamePhase.INITIAL_PLACEMENT:
                    self._random_place(game)
                elif game.phase == GamePhase.PLACE_ARMIES:
                    self._random_place(game)
                    game.next_phase()
                elif game.phase == GamePhase.BATTLE:
                    if random.random() < 0.6:
                        self._random_attack(game)
                    else:
                        game.next_phase()
                elif game.phase == GamePhase.MOVE:
                    if random.random() < 0.3:
                        self._random_fortify(game)
                    else:
                        game.next_phase()
            except Exception as e:
                print(f"[AI Error] {self.name} encountered error: {e}")
                game.next_phase()
            time.sleep(0.3)

    def _random_place(self, game: GameManager):
        player = game.get_current_player()
        my_territories = [t for t in game.territories.values() if t.owner == player]
        if not my_territories:
            return
        target = random.choice(my_territories)
        count = game.reinforcements_to_place
        if count > 0:
            game.place_armies(target.name, count)

    def _random_attack(self, game: GameManager):
        player = game.get_current_player()
        valid_sources = []
        for t in game.territories.values():
            if t.owner == player and t.units > 1:
                targets = [adj for adj in t.adjacent if game.territories[adj].owner != player]
                if targets:
                    valid_sources.append((t, targets))
        if not valid_sources:
            game.next_phase()
            return
        source, targets = random.choice(valid_sources)
        target = random.choice(targets)
        game.attack(source.name, target, 3)

    def _random_fortify(self, game: GameManager):
        player = game.get_current_player()
        valid_sources = []
        for t in game.territories.values():
            if t.owner == player and t.units > 1:
                targets = [adj for adj in t.adjacent if game.territories[adj].owner == player]
                if targets:
                    valid_sources.append((t, targets))
        if not valid_sources:
            game.next_phase()
            return
        source, targets = random.choice(valid_sources)
        target = random.choice(targets)
        count = random.randint(1, source.units - 1)
        game.fortify(source.name, target, count)


def create_game_tools(game: GameManager):
    def get_state_tool() -> str:
        """Returns the current game state, including map territories and your available reinforcements."""
        state = game.get_player_state(game.get_current_player().name)
        return json.dumps(state)

    def place_armies_tool(territory_name: str, count: int) -> str:
        """Places the specified number of armies on a territory you own."""
        success = game.place_armies(territory_name, count)
        if success:
            return f"Successfully placed {count} armies on {territory_name}."
        return "Failed to place armies. Check phase, ownership, and available reinforcements."

    def attack_tool(attacker_name: str, defender_name: str, attacker_dice: int) -> str:
        """Attacks an adjacent enemy territory from one of your territories with the specified number of dice (1-3)."""
        res = game.attack(attacker_name, defender_name, attacker_dice)
        if res:
            return f"Attack result: {res}. Conquered: {res['conquered']}."
        return "Failed to attack. Check adjacency, ownership, and unit counts."

    def fortify_tool(from_t_name: str, to_t_name: str, count: int) -> str:
        """Moves armies from one of your territories to an adjacent territory you own."""
        success = game.fortify(from_t_name, to_t_name, count)
        if success:
            return f"Successfully fortified {to_t_name} from {from_t_name}."
        return "Failed to fortify. Check adjacency, ownership, and unit counts."

    def end_phase_tool() -> str:
        """Ends your current phase. Use this when you are done attacking or fortifying."""
        success = game.next_phase()
        if success:
            return "Phase ended successfully."
        return "Could not end phase right now."

    return [
        StructuredTool.from_function(get_state_tool),
        StructuredTool.from_function(place_armies_tool),
        StructuredTool.from_function(attack_tool),
        StructuredTool.from_function(fortify_tool),
        StructuredTool.from_function(end_phase_tool),
    ]


class TerritoryAgent:
    def __init__(self, name: str, starting_territory: str):
        self.name = name
        self.territories = [starting_territory]
        self.crew_agent = Agent(
            role=f"Commander of {starting_territory}",
            goal=f"Defend your territories and expand your faction's influence. Current territories: {', '.join(self.territories)}",
            backstory=f"You are a seasoned military commander for {starting_territory}.",
            verbose=False,
            allow_delegation=True,
            llm=get_llm()
        )

    def update_goal(self):
        self.crew_agent.goal = (
            f"Defend your territories and expand your faction's influence. "
            f"Current territories: {', '.join(self.territories)}"
        )


class CrewAIFaction:
    """
    A CrewAI-powered faction that uses an automatic scoring system to
    generate performance feedback injected into each successive turn prompt.
    No human interaction required — scoring is fully automatic.
    """

    def __init__(self, player_name: str, scoring_enabled: bool = True):
        self.name = player_name
        self.agents: List[TerritoryAgent] = []
        self.initialized = False
        self.scoring_enabled = scoring_enabled
        self.last_score: Optional[TurnScore] = None
        self.turn_history: List[Dict] = []  # Persisted score history

    def _sync_territories(self, game: GameManager):
        player = game.get_current_player()
        my_territory_names = [t.name for t in game.territories.values() if t.owner == player]

        if not self.initialized:
            for t_name in my_territory_names:
                self.agents.append(TerritoryAgent(f"Agent_{t_name}", t_name))
            self.initialized = True
            return

        for agent in list(self.agents):
            agent.territories = [t for t in agent.territories if t in my_territory_names]
            if not agent.territories:
                self.agents.remove(agent)
            else:
                agent.update_goal()

        assigned = {t for a in self.agents for t in a.territories}
        unassigned = [t for t in my_territory_names if t not in assigned]
        for t in unassigned:
            if self.agents:
                random.choice(self.agents).territories.append(t)

        for agent in self.agents:
            agent.update_goal()

    def _score_and_feedback(self, game: GameManager) -> str:
        """Score the faction BEFORE the turn and produce coaching text for the prompt."""
        if not self.scoring_enabled:
            return ""

        player = next((p for p in game.players if p.name == self.name), None)
        if player is None:
            return ""

        current_score = _scorer.score_player(game, player)
        feedback = _scorer.generate_feedback(current_score, self.last_score)

        # Store for next turn delta calculation
        self.last_score = current_score
        self.turn_history.append(current_score.to_dict())

        print(f"[SCORE] {self.name}: {current_score.total:.1f}/100 — {feedback[:80]}...")
        return feedback

    def execute_turn(self, game: GameManager):
        self._sync_territories(game)

        if not self.agents:
            return

        # Score the current state and get coaching text
        coaching = self._score_and_feedback(game)

        tools = create_game_tools(game)
        for agent in self.agents:
            agent.crew_agent.tools = tools

        phase_name = game.phase.name
        print(f"[AI] {self.name} starting CrewAI turn. Phase: {phase_name}")

        task_desc = ""
        if phase_name == "INITIAL_PLACEMENT":
            task_desc = (
                f"Use 'place_armies_tool' to place exactly {game.reinforcements_to_place} armies "
                f"on one of your territories. DO NOT place more than {game.reinforcements_to_place}."
            )
        elif phase_name == "PLACE_ARMIES":
            task_desc = (
                f"Use 'place_armies_tool' to place {game.reinforcements_to_place} armies across "
                f"your territories strategically. When done, use 'end_phase_tool'."
            )
        elif phase_name == "BATTLE":
            task_desc = (
                f"Evaluate the map. Use 'attack_tool' to attack enemy territories where you have "
                f"an advantage. When done, use 'end_phase_tool'."
            )
        elif phase_name == "MOVE":
            task_desc = (
                f"Use 'fortify_tool' to consolidate armies to border territories. "
                f"When done, use 'end_phase_tool'."
            )

        if not task_desc:
            return

        # Inject the automated coaching feedback into the task
        coaching_block = (
            f"\n\n--- PERFORMANCE COACH (AUTO-SCORED) ---\n{coaching}\n"
            f"Use this analysis to improve your decisions this turn.\n"
            f"---"
        ) if coaching else ""

        task = Task(
            description=(
                f"{task_desc}\n\nUse 'get_state_tool' to see the current map state."
                f"{coaching_block}"
            ),
            expected_output="A brief summary of what actions were taken.",
            agent=self.agents[0].crew_agent
        )

        crew = Crew(
            agents=[a.crew_agent for a in self.agents],
            tasks=[task],
            process=Process.sequential,
            verbose=False
        )

        try:
            crew.kickoff()
        except Exception as e:
            print(f"[AI Error] {self.name} failed CrewAI task: {e}")

        # Failsafe: ensure the phase advances
        if phase_name != "INITIAL_PLACEMENT" and game.phase.name == phase_name:
            if phase_name == "PLACE_ARMIES" and game.reinforcements_to_place > 0:
                t = random.choice([a.territories[0] for a in self.agents if a.territories])
                game.place_armies(t, game.reinforcements_to_place)
            game.next_phase()


class SimulationManager:
    def __init__(self):
        self.simulations: Dict[str, GameManager] = {}
        self.autoplay_active: Dict[str, bool] = {}
        self.ai_factions: Dict[str, Dict[str, CrewAIFaction]] = {}
        self.base_agents: Dict[str, Dict[str, BaseAgent]] = {}
        # Per-simulation score snapshots: {sim_id: {player_name: TurnScore}}
        self.latest_scores: Dict[str, Dict[str, Dict]] = {}
        # Per-simulation scoring toggle
        self.scoring_enabled: Dict[str, bool] = {}

    def create_simulation(self, players_config: List[Dict[str, str]], scoring_enabled: bool = True) -> str:
        sim_id = str(uuid.uuid4())[:8]
        player_names = [p["name"] for p in players_config]
        game = GameManager(player_names)

        self.ai_factions[sim_id] = {}
        self.base_agents[sim_id] = {}
        self.latest_scores[sim_id] = {}
        self.scoring_enabled[sim_id] = scoring_enabled

        for i, p_config in enumerate(players_config):
            p_name = p_config["name"]
            agent_type = p_config.get("agent_type", "human")

            if agent_type != "human":
                game.players[i].is_ai = True
                if agent_type == "crew":
                    self.ai_factions[sim_id][p_name] = CrewAIFaction(p_name, scoring_enabled=scoring_enabled)
                elif agent_type == "base":
                    self.base_agents[sim_id][p_name] = BaseAgent(p_name)

        self.simulations[sim_id] = game
        self.autoplay_active[sim_id] = False
        return sim_id

    def toggle_scoring(self, sim_id: str, enabled: bool):
        """Enable or disable auto-scoring for a running simulation."""
        self.scoring_enabled[sim_id] = enabled
        for faction in self.ai_factions.get(sim_id, {}).values():
            faction.scoring_enabled = enabled
        print(f"[SCORING] Sim {sim_id}: auto-scoring {'ENABLED' if enabled else 'DISABLED'}")

    def create_batch(self, count: int, players_config: List[Dict[str, str]], scoring_enabled: bool = True) -> List[str]:
        ids = []
        for i in range(count):
            batch_config = [
                {"name": f"B{i}_{p['name']}", "agent_type": p["agent_type"]}
                for p in players_config
            ]
            sim_id = self.create_simulation(batch_config, scoring_enabled=scoring_enabled)
            ids.append(sim_id)
            self.start_autoplay(sim_id)
        return ids

    def get_scores(self, sim_id: str) -> Dict[str, Dict]:
        """Return the latest score snapshot for every player in a simulation."""
        game = self.simulations.get(sim_id)
        if not game:
            return {}
        scores = {}
        for player in game.players:
            score = _scorer.score_player(game, player)
            scores[player.name] = score.to_dict()
            # Also cache it
            self.latest_scores.setdefault(sim_id, {})[player.name] = score.to_dict()
        return scores

    def start_autoplay(self, sim_id: str):
        if sim_id in self.simulations and not self.autoplay_active[sim_id]:
            self.autoplay_active[sim_id] = True
            thread = threading.Thread(target=self._autoplay_loop, args=(sim_id,), daemon=True)
            thread.start()

    def stop_autoplay(self, sim_id: str):
        self.autoplay_active[sim_id] = False

    def _autoplay_loop(self, sim_id: str):
        game = self.simulations[sim_id]
        factions = self.ai_factions[sim_id]
        base_agents = self.base_agents[sim_id]

        while self.autoplay_active.get(sim_id, False):
            current_p = game.get_current_player()
            if current_p.is_ai:
                faction = factions.get(current_p.name)
                base_agent = base_agents.get(current_p.name)

                if faction:
                    faction.execute_turn(game)
                elif base_agent:
                    base_agent.execute_turn(game)
                else:
                    BaseAgent(current_p.name).execute_turn(game)
            else:
                time.sleep(1)
            time.sleep(0.5)


# Global Simulation Manager instance
simulation_manager = SimulationManager()
