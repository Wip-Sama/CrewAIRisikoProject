import os
import json
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Dict, List, Optional
import map as game_map
from data import UnitType, GamePhase
from ai_agents import simulation_manager

app = FastAPI(title="Risiko AI Engine")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

resources_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "resources"))
if os.path.exists(resources_path):
    app.mount("/assets", StaticFiles(directory=resources_path), name="assets")


class PlayerConfig(BaseModel):
    name: str
    agent_type: str  # 'human', 'base', 'crew'


class BatchCreateRequest(BaseModel):
    batch_count: int
    players: List[PlayerConfig]
    scoring: bool = True  # Whether auto-scoring feedback is injected into CrewAI prompts
    max_agents_per_faction: int = -1


class ReinforceRequest(BaseModel):
    territory: str
    count: int


class AttackRequest(BaseModel):
    attacker: str
    defender: str
    attacker_count: int  # Total units committed; dice are capped at 3 internally


class FortifyRequest(BaseModel):
    from_territory: str
    to_territory: str
    count: int


class TradeRequest(BaseModel):
    cards: List[str]


def get_game(sim_id: str, check_human: bool = True):
    game = simulation_manager.simulations.get(sim_id)
    if not game:
        raise HTTPException(status_code=404, detail="Simulation not found")
    if check_human and not game.is_human_turn():
        raise HTTPException(status_code=403, detail="It is currently an AI's turn")
    return game


@app.get("/api/simulations/list")
async def list_simulations():
    return [
        {
            "id": k,
            "phase": v.phase.name,
            "current_player": v.get_current_player().name,
            "is_ai_turn": not v.is_human_turn(),
            "scoring_enabled": simulation_manager.scoring_enabled.get(k, True),
        }
        for k, v in simulation_manager.simulations.items()
    ]


@app.post("/api/simulations/create_batch")
async def create_batch(req: BatchCreateRequest):
    configs = [{"name": p.name, "agent_type": p.agent_type} for p in req.players]
    ids = simulation_manager.create_batch(
        req.batch_count, 
        configs, 
        scoring_enabled=req.scoring,
        max_agents_per_faction=req.max_agents_per_faction
    )
    return {"simulation_ids": ids, "scoring_enabled": req.scoring}


class ToggleScoringRequest(BaseModel):
    sim_id: str
    enabled: bool


@app.post("/api/simulations/toggle_scoring")
async def toggle_scoring(req: ToggleScoringRequest):
    if req.sim_id not in simulation_manager.simulations:
        raise HTTPException(status_code=404, detail="Simulation not found")
    simulation_manager.toggle_scoring(req.sim_id, req.enabled)
    return {"sim_id": req.sim_id, "scoring_enabled": req.enabled}


@app.get("/api/simulations/scores")
async def get_scores(sim_id: str):
    """
    Returns the latest auto-computed score for every player in the simulation.
    Scores are computed from the live game state on each request.
    """
    if sim_id not in simulation_manager.simulations:
        raise HTTPException(status_code=404, detail="Simulation not found")
    scores = simulation_manager.get_scores(sim_id)
    return {
        "scores": scores,
        "scoring_enabled": simulation_manager.scoring_enabled.get(sim_id, True),
    }


@app.get("/api/state")
async def get_state(sim_id: str):
    game = get_game(sim_id, check_human=False)
    state = game.get_state()
    state["sim_id"] = sim_id
    state["is_human_turn"] = game.is_human_turn()
    return state


@app.post("/api/action/reinforce")
async def reinforce(req: ReinforceRequest, sim_id: str):
    game = get_game(sim_id)
    success = game.place_armies(req.territory, req.count)
    if not success:
        raise HTTPException(status_code=400, detail="Invalid reinforcement")
    return game.get_state()


@app.post("/api/action/attack")
async def attack(req: AttackRequest, sim_id: str):
    game = get_game(sim_id)
    result = game.attack(req.attacker, req.defender, req.attacker_count)
    if result is None:
        raise HTTPException(status_code=400, detail="Invalid attack")
    return {"result": result, "state": game.get_state()}


@app.post("/api/action/fortify")
async def fortify(req: FortifyRequest, sim_id: str):
    game = get_game(sim_id)
    success = game.fortify(req.from_territory, req.to_territory, req.count)
    if not success:
        raise HTTPException(status_code=400, detail="Invalid fortification")
    return game.get_state()


@app.post("/api/action/trade_cards")
async def trade_cards(req: TradeRequest, sim_id: str):
    game = get_game(sim_id)
    success = game.trade_cards(req.cards)
    if not success:
        raise HTTPException(status_code=400, detail="Invalid card combination")
    return game.get_state()


@app.post("/api/action/next_phase")
async def next_phase(sim_id: str):
    game = get_game(sim_id)
    success = game.next_phase()
    if not success:
        raise HTTPException(status_code=400, detail="Cannot advance phase yet")
    return game.get_state()


@app.get("/api/map-info")
async def get_map_info():
    return {
        "continents": game_map.continents,
        "bonus": game_map.continentsBonus,
        "mapping": game_map.territoryImageMapping,
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
