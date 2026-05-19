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

from crewai import Agent, Task, Crew, Process, LLM
from crewai.tools import tool
import json
import logging

logging.getLogger("crewai").setLevel(logging.WARNING)

# Directory where score history is persisted
TRAINING_DIR = os.path.join(os.path.dirname(__file__), "training_data")
os.makedirs(TRAINING_DIR, exist_ok=True)

_scorer = GameScorer()

# LLM Configuration
def get_llm(provider=None):
    """
    Returns a configured crewai.LLM instance based on .env settings.
    """
    if not provider:
        provider = os.getenv("MODEL_PROVIDER", "groq").lower()
    
    try:
        if provider == "openai":
            api_key = os.getenv("OPENAI_API_KEY")
            return LLM(model=os.getenv("OPENAI_MODEL_NAME", "gpt-4o"), api_key=api_key)
        elif provider == "google":
            api_key = os.getenv("GOOGLE_API_KEY")
            model_name = os.getenv("GOOGLE_MODEL_NAME", "gemini-2.0-flash")
            # Both Gemini and Gemma models use 'gemini/' prefix for LiteLLM
            if not model_name.startswith(("gemini/", "vertex_ai/")):
                model_name = f"gemini/{model_name}"
            return LLM(model=model_name, api_key=api_key)
        elif provider == "groq":
            api_key = os.getenv("GROQ_API_KEY")
            model_name = os.getenv("GROQ_MODEL_NAME", "groq/llama-3.1-8b-instant")
            # Groq needs 'groq/' prefix for LiteLLM
            if not model_name.startswith("groq/"):
                model_name = f"groq/{model_name}"
            return LLM(model=model_name, api_key=api_key)
        elif provider == "ollama":
            model_name = os.getenv("OLLAMA_MODEL_NAME", "gemma")
            base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
            return LLM(
                model=f"ollama/{model_name}",
                base_url=base_url
            )
        elif provider == "qwen":
            api_key = os.getenv("QWEN_API_KEY")
            model_name = os.getenv("QWEN_MODEL_NAME", "qwen-plus")
            base_url = os.getenv("QWEN_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
            return LLM(
                model=f"openai/{model_name}",
                base_url=base_url,
                api_key=api_key
            )
        elif provider == "lmstudio":
            model_name = os.getenv("LMSTUDIO_MODEL_NAME", "local-model")
            return LLM(
                model=f"openai/{model_name}",
                base_url=os.getenv("LMSTUDIO_BASE_URL", "http://localhost:1234/v1"),
                api_key="not-needed"
            )
    except Exception as e:
        print(f"[LLM Error] Failed to initialize {provider} provider: {e}")
    return None


def create_game_tools(game: GameManager):
    @tool("get_state_tool")
    def get_state_tool(reason: str) -> str:
        """Returns the current game state, including map territories and your available reinforcements. 
        Provide a brief reason for requesting the state (e.g., 'Planning attack')."""
        state = game.get_player_state(game.get_current_player().name)
        return json.dumps(state)

    @tool("place_armies_tool")
    def place_armies_tool(territory_name: str, count: int) -> str:
        """Places the specified number of armies on a territory you own. 
        You can call this multiple times to split your total reinforcements across different territories."""
        success = game.place_armies(territory_name, count)
        if success:
            return f"Successfully placed {count} armies on {territory_name}."
        return "Failed to place armies. Check phase, ownership, and available reinforcements."

    @tool("attack_tool")
    def attack_tool(attacker_name: str, defender_name: str, attacker_dice: int) -> str:
        """Attacks an adjacent enemy territory from one of your territories with the specified number of dice (1-3). 
        You can call this multiple times per turn to launch several attacks or strike from different fronts."""
        res = game.attack(attacker_name, defender_name, attacker_dice)
        if res:
            return f"Attack result: {res}. Conquered: {res['conquered']}."
        return "Failed to attack. Check adjacency, ownership, and unit counts."

    @tool("trade_cards_tool")
    def trade_cards_tool(card_names: str) -> str:
        """Trade a set of 3 cards (comma-separated names) for bonus reinforcements. Valid sets: Jolly+2same(+12), 1ofeach(+10), 3same(+8). Call get_state_tool first to see your cards."""
        try:
            cards = [c.strip() for c in card_names.split(',')]
            if len(cards) != 3:
                return "Error: Provide exactly 3 card names separated by commas."
            
            # Check if player actually owns these cards and if they form a set
            player = game.get_current_player()
            if not all(c in player.cards for c in cards):
                return f"Error: You do not own some of these cards: {cards}"
            
            success = game.trade_cards(cards)
            if success:
                return f"Success: Cards {cards} traded! New reinforcements available: {game.reinforcements_to_place}."
            return f"Error: {cards} do not form a valid set. Valid sets: Jolly+2same(+12), 1ofeach(+10), 3same(+8)."
        except Exception as e:
            return f"Error trading cards: {e}"

    @tool("fortify_tool")
    def fortify_tool(from_t_name: str, to_t_name: str, count: int) -> str:
        """Moves armies from one of your territories to an adjacent territory you own."""
        success = game.fortify(from_t_name, to_t_name, count)
        if success:
            return f"Successfully fortified {to_t_name} from {from_t_name}."
        return "Failed to fortify. Check adjacency, ownership, and unit counts."

    @tool("end_phase_tool")
    def end_phase_tool(confirmation: bool) -> str:
        """Ends your current phase. Use this when you are done attacking or fortifying. 
        Set confirmation=True to proceed."""
        if not confirmation:
            return "Phase not ended because confirmation was False."
        success = game.next_phase()
        if success:
            return "Phase ended successfully."
        return "Could not end phase right now."

    return [
        get_state_tool,
        place_armies_tool,
        attack_tool,
        fortify_tool,
        end_phase_tool,
        trade_cards_tool,
    ]


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
                    self._use_card(game)  # Use any available card sets first
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

    def _use_card(self, game: GameManager):
        """Greedily trade all valid card sets for bonus reinforcements."""
        player = game.get_current_player()
        while True:
            best_set = game.get_tradeable_set(player)
            if best_set is None:
                break
            success = game.trade_cards(best_set)
            if not success:
                break
            print(f"[AI] {self.name} traded cards {best_set} for bonus reinforcements")

    def _random_place(self, game: GameManager):
        player = game.get_current_player()
        my_territories = [t for t in game.territories.values() if t.owner == player]
        if not my_territories:
            return
        
        while game.reinforcements_to_place > 0:
            # Randomly split reinforcements: place between 1 and the total remaining
            # but usually in smaller chunks to encourage variety
            max_chunk = max(1, game.reinforcements_to_place // 2 + 1)
            count = random.randint(1, min(game.reinforcements_to_place, max_chunk))
            
            # During INITIAL_PLACEMENT, we are limited to 3 per turn anyway
            if game.phase == GamePhase.INITIAL_PLACEMENT:
                count = min(count, game.reinforcements_to_place)

            target = random.choice(my_territories)
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


class TerritoryAgent:
    def __init__(self, name: str, starting_territory: str, llm=None):
        self.name = name
        self.territories = [starting_territory]
        self.crew_agent = Agent(
            role=f"Commander of {starting_territory}",
            goal=f"Defend your territories and expand your faction's influence. Current territories: {', '.join(self.territories)}",
            backstory=f"You are a seasoned military commander for {starting_territory}.",
            verbose=False,
            allow_delegation=True,
            llm=llm if llm else get_llm()
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

    def __init__(self, player_name: str, scoring_enabled: bool = True, provider: str = None, max_agents_per_faction: int = -1):
        self.name = player_name
        self.agents: List[TerritoryAgent] = []
        self.initialized = False
        self.scoring_enabled = scoring_enabled
        self.last_score: Optional[TurnScore] = None
        self.turn_history: List[Dict] = []  # Persisted score history
        self.llm = get_llm(provider)
        self.max_agents_per_faction = max_agents_per_faction

    def _sync_territories(self, game: GameManager):
        player = game.get_current_player()
        my_territory_names = [t.name for t in game.territories.values() if t.owner == player]

        if not self.initialized:
            num_territories = len(my_territory_names)
            limit = self.max_agents_per_faction
            
            if limit <= 0 or limit >= num_territories:
                # Default behavior: one agent per territory
                for t_name in my_territory_names:
                    self.agents.append(TerritoryAgent(f"Agent_{t_name}", t_name, llm=self.llm))
            else:
                # Limited agents: split territories as equally as possible
                # Example: 21 territories, 5 agents -> 5, 4, 4, 4, 4
                chunk_size = num_territories // limit
                remainder = num_territories % limit
                
                start_idx = 0
                for i in range(limit):
                    # Distribute the remainder across the first few agents
                    current_chunk_size = chunk_size + (1 if i < remainder else 0)
                    end_idx = start_idx + current_chunk_size
                    
                    agent_territories = my_territory_names[start_idx:end_idx]
                    if agent_territories:
                        # Use the first territory as the "starting" one for naming/role
                        agent = TerritoryAgent(f"Commander_{i+1}", agent_territories[0], llm=self.llm)
                        agent.territories = agent_territories
                        agent.update_goal()
                        self.agents.append(agent)
                    
                    start_idx = end_idx
            
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
            player = next((p for p in game.players if p.name == self.name), None)
            cards_info = ""
            if player and len(player.cards) >= 3:
                best_set = game.get_tradeable_set(player)
                if best_set:
                    cards_info = (
                        f"\n\nIMPORTANT — You hold cards: {player.cards}. "
                        f"A valid tradeable set was detected: {best_set}. "
                        f"Use 'trade_cards_tool' with these card names (comma-separated) to gain bonus reinforcements BEFORE placing armies. "
                        f"You may also trade additional sets if you have more cards."
                    )
                else:
                    cards_info = f"\n\nYou hold {len(player.cards)} cards but no tradeable set yet."
            task_desc = (
                f"Use 'place_armies_tool' to place {game.reinforcements_to_place} armies across "
                f"your territories strategically. You can call the tool multiple times to split "
                f"reinforcements between different territories. When done, use 'end_phase_tool'."
                f"{cards_info}"
            )
        elif phase_name == "BATTLE":
            task_desc = (
                f"Evaluate the map. Use 'attack_tool' to attack enemy territories where you have "
                f"an advantage. You can attack multiple times per turn and on multiple fronts. "
                f"When done, use 'end_phase_tool'."
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

        # Rate-limit delay between API requests
        delay = float(os.getenv("REQUEST_DELAY", 0))
        if delay > 0:
            time.sleep(delay)

        # Failsafe: ensure the phase advances
        if phase_name != "INITIAL_PLACEMENT" and game.phase.name == phase_name:
            if phase_name == "PLACE_ARMIES" and game.reinforcements_to_place > 0:
                player = game.get_current_player()
                my_territories = [t.name for t in game.territories.values() if t.owner == player]
                if my_territories:
                    while game.reinforcements_to_place > 0:
                        t = random.choice(my_territories)
                        # Small batches for failsafe distribution
                        amt = random.randint(1, min(game.reinforcements_to_place, 3))
                        game.place_armies(t, amt)
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

    def create_simulation(self, players_config: List[Dict[str, str]], scoring_enabled: bool = True, max_agents_per_faction: int = -1) -> str:
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
                if agent_type.startswith("crew"):
                    parts = agent_type.split(":")
                    provider = parts[1] if len(parts) > 1 else None
                    self.ai_factions[sim_id][p_name] = CrewAIFaction(
                        p_name, 
                        scoring_enabled=scoring_enabled, 
                        provider=provider,
                        max_agents_per_faction=max_agents_per_faction
                    )
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

    def create_batch(self, count: int, players_config: List[Dict[str, str]], scoring_enabled: bool = True, max_agents_per_faction: int = -1) -> List[str]:
        ids = []
        for i in range(count):
            batch_config = [
                {"name": f"B{i}_{p['name']}", "agent_type": p["agent_type"]}
                for p in players_config
            ]
            sim_id = self.create_simulation(
                batch_config, 
                scoring_enabled=scoring_enabled,
                max_agents_per_faction=max_agents_per_faction
            )
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
