import { useState, useEffect } from 'react'
import axios from 'axios'
import { motion, AnimatePresence } from 'framer-motion'
import { Users, Activity, ArrowRight, Plus, Swords, History } from 'lucide-react'
import { useRef as reactRef } from 'react'
import { PixelPerfectMap } from './components/PixelPerfectMap'
import './App.css'

interface Territory {
  name: string
  owner: string
  owner_color: string
  units: number
  type: string
  image_id: string
  adjacent: string[]
}

interface Player {
  name: string
  color: string
  territories: number
  objective?: {
    description: string
    type: string
  }
  cards: { name: string, type: string }[]
  predicted_reinforcements: number
}

interface DiceResult {
  attacker_rolls: number[]
  defender_rolls: number[]
  attacker_losses: number
  defender_losses: number
  conquered: boolean
}

interface GameState {
  phase: string
  current_player: string
  reinforcements: number
  last_dice_roll: DiceResult | null
  territories: Record<string, Territory>
  players: Player[]
  is_human_turn: boolean
  sim_id: string
  winner: string | null
  win_reason: string
}

function App() {
  const [gameState, setGameState] = useState<GameState | null>(null)
  const [selectedTerritory, setSelectedTerritory] = useState<Territory | null>(null)
  const [targetTerritory, setTargetTerritory] = useState<Territory | null>(null)
  const [hoveredPlayer, setHoveredPlayer] = useState<string | null>(null)
  const [diceCount, setDiceCount] = useState<number>(3)
  const [hoveredCard, setHoveredCard] = useState<{ name: string, type: string } | null>(null)
  const [selectedCards, setSelectedCards] = useState<string[]>([])
  const [moveCount, setMoveCount] = useState<number>(1)
  const [hoveredPlayerTop, setHoveredPlayerTop] = useState<number>(0)
  const logRef = reactRef<HTMLDivElement>(null)
  const [simulationId, setSimulationId] = useState<string>("")
  const [simulationList, setSimulationList] = useState<any[]>([])
  const [showBatchModal, setShowBatchModal] = useState(true)
  const [playerScores, setPlayerScores] = useState<Record<string, any>>({})
  const [scoringEnabled, setScoringEnabled] = useState<boolean>(true)

  const defaultPlayerNames = ["Commander Alpha", "General Bravo", "Colonel Charlie", "Major Delta", "Captain Echo", "Lieutenant Foxtrot"]
  const [batchConfig, setBatchConfig] = useState({
    count: 1,
    scoring: true,
    players: defaultPlayerNames.slice(0, 4).map(name => ({ name, agent_type: 'human' }))
  })

  const fetchState = async () => {
    try {
      const listRes = await axios.get('/api/simulations/list')
      setSimulationList(listRes.data)

      if (!simulationId && listRes.data.length > 0) {
        setSimulationId(listRes.data[0].id)
        setShowBatchModal(false)
        return
      }

      if (simulationId) {
        const stateRes = await axios.get(`/api/state?sim_id=${simulationId}`)
        setGameState(stateRes.data)

        if (selectedTerritory) setSelectedTerritory(stateRes.data.territories[selectedTerritory.name])
        if (targetTerritory) setTargetTerritory(stateRes.data.territories[targetTerritory.name])

        if (logRef.current) {
          logRef.current.scrollTop = logRef.current.scrollHeight;
        }
      } else {
        setGameState(null)
      }
    } catch (error) {
      console.error("Failed to fetch state", error)
    }
  }

  const fetchScores = async () => {
    if (!simulationId) return
    try {
      const res = await axios.get(`/api/simulations/scores?sim_id=${simulationId}`)
      setPlayerScores(res.data.scores ?? {})
      setScoringEnabled(res.data.scoring_enabled ?? true)
    } catch { /* scores are best-effort */ }
  }

  const handleToggleScoring = async () => {
    if (!simulationId) return
    const next = !scoringEnabled
    setScoringEnabled(next)
    try {
      await axios.post('/api/simulations/toggle_scoring', { sim_id: simulationId, enabled: next })
    } catch { setScoringEnabled(!next) /* revert on failure */ }
  }

  useEffect(() => {
    fetchState()
    const interval = setInterval(fetchState, 3000)
    return () => clearInterval(interval)
  }, [selectedTerritory?.name, targetTerritory?.name, simulationId])

  useEffect(() => {
    fetchScores()
    const interval = setInterval(fetchScores, 5000)
    return () => clearInterval(interval)
  }, [simulationId])

  const handleAction = async (action: string, payload: any = {}) => {
    try {
      await axios.post(`/api/action/${action}?sim_id=${simulationId}`, payload)
      fetchState()
    } catch (error: any) {
      alert(error.response?.data?.detail || "Action failed")
    }
  }

  const handleCreateBatch = async () => {
    try {
      const res = await axios.post('/api/simulations/create_batch', {
        batch_count: batchConfig.count,
        players: batchConfig.players,
        scoring: batchConfig.scoring
      })
      const newId = res.data.simulation_ids[0]
      setSimulationId(newId)
      setScoringEnabled(batchConfig.scoring)
      setShowBatchModal(false)
      fetchState()
    } catch (error: any) {
      alert("Failed to create batch")
    }
  }

  if (!gameState && !showBatchModal) return <div className="loading">Loading Engine...</div>

  const isCurrentPlayer = (owner: string) => gameState ? owner === gameState.current_player : false

  const isValidTrade = (selectedNames: string[]) => {
    if (selectedNames.length !== 3 || !gameState) return false
    const player = gameState.players.find(p => p.name === gameState.current_player)
    if (!player) return false
    const selected = player.cards.filter(c => selectedNames.includes(c.name))
    if (selected.length !== 3) return false

    const counts: Record<string, number> = {}
    selected.forEach(c => counts[c.type] = (counts[c.type] || 0) + 1)

    const jolly = counts['JOLLY'] || 0
    const fante = counts['FANTE'] || 0
    const cavallo = counts['CAVALLO'] || 0
    const cannone = counts['CANNONE'] || 0

    // Match backend logic in game_logic.py:
    // 1 Jolly + 2 of same type
    if (jolly === 1 && (fante === 2 || cavallo === 2 || cannone === 2)) return true
    // 1 of each type
    if (fante === 1 && cavallo === 1 && cannone === 1) return true
    // 3 of same type
    if (fante === 3 || cavallo === 3 || cannone === 3) return true

    return false
  }

  const getNextPhase = () => {
    if (!gameState) return '...'
    switch (gameState.phase) {
      case 'PLACE_ARMIES': return 'BATTLE'
      case 'BATTLE': return 'MOVE'
      case 'MOVE': return 'PLACE ARMIES (Next Turn)'
      default: return '...'
    }
  }

  return (
    <div className="app-container">
      {/* Sidebar */}
      <aside className="sidebar">
        <div className="sidebar-header">
          <Activity className="accent-icon" />
          <h1 className="title">Risiko AI</h1>
        </div>

        <div className="simulation-manager glass-panel" style={{ padding: '0.75rem', marginBottom: '1rem' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem' }}>
            <span className="section-label">Simulation</span>
            <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
              {simulationId && (
                <button
                  className={`btn-icon scoring-toggle-btn ${scoringEnabled ? 'scoring-on' : 'scoring-off'}`}
                  onClick={handleToggleScoring}
                  title={scoringEnabled ? 'Auto-Scoring ON — click to disable' : 'Auto-Scoring OFF — click to enable'}
                >
                  <Activity size={13} />
                </button>
              )}
              <button className="btn-icon" onClick={() => setShowBatchModal(true)} title="Create New Batch">
                <Plus size={14} />
              </button>
            </div>
          </div>
          <select
            value={simulationId}
            onChange={(e) => setSimulationId(e.target.value)}
            className="sim-select"
          >
            {simulationList.map(sim => (
              <option key={sim.id} value={sim.id}>
                {sim.id} ({sim.phase}) {sim.is_ai_turn ? '🤖' : '👤'}{sim.scoring_enabled ? ' 📊' : ''}
              </option>
            ))}
          </select>
        </div>

        {gameState && (
          <>
            <div className="glass-panel stat-card" style={{ border: gameState.is_human_turn ? '1px solid var(--accent-color)' : '1px solid #ef4444' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span className="stat-label">Current Phase</span>
                {!gameState.is_human_turn && gameState.phase !== 'ENDGAME' && <span className="ai-badge">AI Thinking...</span>}
              </div>
              <span className="stat-value accent-text">{gameState.phase.replace(/_/g, ' ')}</span>
            </div>
            <div className="phase-preview">
              {gameState.phase === 'INITIAL_PLACEMENT' ? 'Distributing starting forces...' : gameState.phase === 'ENDGAME' ? 'Game Over' : `Next: ${getNextPhase()}`}
            </div>
          </>
        )}

        {gameState && (gameState.phase === 'PLACE_ARMIES' || gameState.phase === 'INITIAL_PLACEMENT') && isCurrentPlayer(gameState.current_player) && (
          <div className="glass-panel stat-card highlight">
            <span className="stat-label">Reinforcements</span>
            <span className="stat-value">{gameState.reinforcements}</span>
          </div>
        )}

        {gameState && (
          <div className="player-list">
            <h3 className="section-label">Commanders</h3>
            {gameState.players.map(p => {
              const score = playerScores[p.name]
              return (
              <div key={p.name} style={{ position: 'relative' }}>
                <div
                  className={`player-item ${p.name === gameState.current_player ? 'active' : ''}`}
                  onMouseEnter={(e) => {
                    setHoveredPlayer(p.name);
                    const rect = e.currentTarget.getBoundingClientRect();
                    const sidebarRect = e.currentTarget.closest('.sidebar')?.getBoundingClientRect();
                    if (sidebarRect) setHoveredPlayerTop(rect.top - sidebarRect.top);
                  }}
                  onMouseLeave={() => setHoveredPlayer(null)}
                >
                  <div className="player-color" style={{ color: p.color, backgroundColor: p.color }} />
                  <div style={{ flex: 1 }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <div style={{ fontWeight: 600, fontSize: '0.9rem' }}>{p.name}</div>
                      <div style={{ display: 'flex', gap: '0.35rem', alignItems: 'center' }}>
                        {score && (
                          <span
                            className="score-badge"
                            title={`Score ${Math.round(score.total)}/100 | T:${Math.round(score.territory_score)} C:${Math.round(score.continent_score)} A:${Math.round(score.army_score)} K:${Math.round(score.card_score)} F:${Math.round(score.frontier_pressure)}`}
                          >
                            {Math.round(score.total)}
                          </span>
                        )}
                        <div className="next-turn-badge" title="Predicted reinforcements next turn">
                          +{p.predicted_reinforcements}
                        </div>
                      </div>
                    </div>
                    <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)', marginBottom: '0.3rem' }}>{p.territories} Territories</div>

                    {/* Score bar */}
                    {score && (
                      <div className="score-bar-container" title={`Score breakdown: T=${Math.round(score.territory_score)} C=${Math.round(score.continent_score)} A=${Math.round(score.army_score)} K=${Math.round(score.card_score)} F=${Math.round(score.frontier_pressure)}`}>
                        <motion.div
                          className="score-bar-fill"
                          animate={{ width: `${Math.min(100, score.total)}%` }}
                          transition={{ duration: 0.8, ease: 'easeOut' }}
                          style={{ background: `linear-gradient(90deg, ${p.color}aa, ${p.color})` }}
                        />
                      </div>
                    )}

                    {/* Cards Display */}
                    {p.cards.length > 0 && (
                      <div className="card-mini-list">
                        {p.cards.map((c, i) => {
                          const isSelectable = gameState.is_human_turn && p.name === gameState.current_player && (gameState.phase === 'PLACE_ARMIES')
                          const isSelected = selectedCards.includes(c.name)
                          return (
                          <div
                            key={`${p.name}-card-${i}`}
                            className={`card-mini ${c.type.toLowerCase()} ${isSelected ? 'selected' : ''} ${isSelectable ? 'selectable' : ''}`}
                            onClick={() => {
                              if (!isSelectable) return
                              setSelectedCards(prev =>
                                prev.includes(c.name)
                                  ? prev.filter(x => x !== c.name)
                                  : prev.length < 3 ? [...prev, c.name] : prev
                              )
                            }}
                            onMouseEnter={() => setHoveredCard({ name: c.name, type: c.type })}
                            onMouseLeave={() => setHoveredCard(null)}
                            style={{ position: 'relative' }}
                          >
                            {c.type[0]}
                            <AnimatePresence>
                              {hoveredCard?.name === c.name && (
                                <motion.div
                                  initial={{ opacity: 0, y: 10 }}
                                  animate={{ opacity: 1, y: 0 }}
                                  exit={{ opacity: 0, y: 10 }}
                                  className="card-tooltip"
                                >
                                  <span className="card-tooltip-name">{c.name}</span>
                                  <span className="card-tooltip-type">{c.type}</span>
                                </motion.div>
                              )}
                            </AnimatePresence>
                          </div>
                        )})}
                      </div>
                    )}

                    {/* Trade Cards button - visible when 3 cards are selected and it's this player's placement turn */}
                    {p.name === gameState.current_player && gameState.is_human_turn && gameState.phase === 'PLACE_ARMIES' && selectedCards.length === 3 && (
                      <button
                        className={`btn-trade-cards ${isValidTrade(selectedCards) ? '' : 'disabled'}`}
                        disabled={!isValidTrade(selectedCards)}
                        onClick={async () => {
                          await handleAction('trade_cards', { cards: selectedCards })
                          setSelectedCards([])
                        }}
                      >
                        {isValidTrade(selectedCards) ? '🃏 Trade Cards (+Bonus)' : '🚫 Invalid Set'}
                      </button>
                    )}
                  </div>
                </div>
              </div>
            )})}
          </div>
        )}

        {/* Global Secret Objective Popup (outside scroll area) */}
        <AnimatePresence>
          {gameState && hoveredPlayer && gameState.players.find(p => p.name === hoveredPlayer)?.objective && (
            <motion.div
              initial={{ opacity: 0, x: -10 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -10 }}
              className="objective-popup"
              style={{ top: hoveredPlayerTop }}
            >
              <div className="popup-tag">Secret Objective</div>
              <p className="objective-desc">{gameState.players.find(p => p.name === hoveredPlayer)?.objective?.description}</p>
            </motion.div>
          )}
        </AnimatePresence>

        {gameState && gameState.phase !== 'ENDGAME' && (
          <div className="action-bar">
            <button
              className="btn-primary"
              onClick={() => handleAction('next_phase')}
              disabled={!gameState.is_human_turn}
            >
              {gameState.is_human_turn ? 'End Phase' : 'AI playing...'} <ArrowRight size={16} />
            </button>
          </div>
        )}

        {gameState && (
          <div className="monitoring-section">
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.2rem' }}>
              <History size={12} className="accent-text" />
              <h3 className="section-label" style={{ margin: 0 }}>Battle Log</h3>
            </div>
            <div className="glass-panel console" ref={logRef}>
              <div className="log-history">
                {gameState.battle_log?.map((log, i) => (
                  <div key={i} className="log-entry">
                    <span className="log-time">[{new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}]</span> {log}
                  </div>
                ))}
              </div>

              {gameState.last_dice_roll && (
                <div className="dice-ui" style={{ marginTop: '0.75rem', borderTop: '1px solid rgba(255,255,255,0.05)', paddingTop: '0.5rem' }}>
                  <div className="dice-container">
                    {gameState.last_dice_roll.attacker_rolls.map((r, i) => (
                      <div key={`att-${i}`} className="die attacker">{r}</div>
                    ))}
                    <span style={{ alignSelf: 'center', margin: '0 4px', fontSize: '0.6rem' }}>vs</span>
                    {gameState.last_dice_roll.defender_rolls.map((r, i) => (
                      <div key={`def-${i}`} className="die defender">{r}</div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>
        )}
      </aside>

      {/* Main Map View */}
      <main className="main-content">
        {gameState && (
          <PixelPerfectMap
            territories={gameState.territories}
            selectedTerritory={selectedTerritory}
            targetTerritory={targetTerritory}
            hoveredPlayer={hoveredPlayer}
            highlightedTerritory={hoveredCard?.name || null}
            isJollyHovered={hoveredCard?.type === 'JOLLY'}
            lastActedTerritory={gameState.last_acted_territory}
            onTerritoryClick={(t) => {
              if (gameState.phase === 'BATTLE' && selectedTerritory && selectedTerritory.owner === gameState.current_player && t.owner !== gameState.current_player) {
                if (selectedTerritory.adjacent.includes(t.name)) {
                  setTargetTerritory(t)
                } else {
                  setSelectedTerritory(t)
                  setTargetTerritory(null)
                }
              } else if (gameState.phase === 'MOVE' && selectedTerritory && selectedTerritory.owner === gameState.current_player && t.owner === gameState.current_player) {
                if (selectedTerritory.adjacent.includes(t.name)) {
                  setTargetTerritory(t)
                  setMoveCount(1)
                } else {
                  setSelectedTerritory(t)
                  setTargetTerritory(null)
                }
              } else {
                setSelectedTerritory(t)
                setTargetTerritory(null)
              }
            }}
          />
        )}

        {/* Territory Info & Actions Overlay */}
        <div className="overlay-container">
          <AnimatePresence>
            {gameState && gameState.phase === 'ENDGAME' && gameState.winner && (
              <motion.div
                initial={{ opacity: 0, y: -20 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -20 }}
                className="info-panel endgame-panel"
                style={{ position: 'absolute', top: '1rem', right: '1rem', border: '2px solid #ef4444', background: 'rgba(20, 20, 25, 0.95)' }}
              >
                <div className="panel-header">
                  <h2 className="panel-title" style={{ color: '#ef4444', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                    <Users size={20} /> Winner: {gameState.winner}
                  </h2>
                </div>
                <div style={{ marginTop: '1rem' }}>
                  <p className="label">Objective Completed</p>
                  <p style={{ fontSize: '0.9rem', color: 'var(--text-primary)', marginTop: '0.25rem' }}>{gameState.win_reason}</p>
                </div>
              </motion.div>
            )}
            {gameState && (selectedTerritory || targetTerritory) && (
              <motion.div
                initial={{ opacity: 0, x: 20 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: 20 }}
                className="info-panel"
              >
                <div className="panel-header">
                  <h2 className="panel-title">
                    {targetTerritory ? `Target: ${targetTerritory.name}` : selectedTerritory?.name}
                  </h2>
                  <button onClick={() => { setSelectedTerritory(null); setTargetTerritory(null); }} className="close-btn">×</button>
                </div>

                <div className="panel-stats">
                  <div>
                    <p className="label">Units</p>
                    <p className="value-large">{targetTerritory ? targetTerritory.units : selectedTerritory?.units}</p>
                  </div>
                  <div>
                    <p className="label">Territory Code</p>
                    <p className="value-small accent-text">ID: {targetTerritory ? targetTerritory.image_id : selectedTerritory?.image_id}</p>
                  </div>
                  <div>
                    <p className="label">Commander</p>
                    <p className="value-small" style={{ color: targetTerritory ? targetTerritory.owner_color : selectedTerritory?.owner_color }}>
                      {targetTerritory ? targetTerritory.owner : selectedTerritory?.owner}
                    </p>
                  </div>
                </div>

                <div className="action-section" style={{ marginTop: '1rem', borderTop: '1px solid var(--glass-border)', paddingTop: '1rem' }}>
                  {(gameState.phase === 'PLACE_ARMIES' || gameState.phase === 'INITIAL_PLACEMENT') && selectedTerritory?.owner === gameState.current_player && gameState.reinforcements > 0 && (
                    <button
                      className="btn-primary"
                      onClick={() => handleAction('reinforce', { territory: selectedTerritory.name, count: 1 })}
                      disabled={!gameState.is_human_turn}
                    >
                      <Plus size={16} /> Deploy Army
                    </button>
                  )}

                  {gameState.phase === 'BATTLE' && selectedTerritory?.owner === gameState.current_player && targetTerritory && (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                      <div className="move-count-display">
                        <p className="label">Units to attack with:</p>
                        <span className="move-value" style={{ color: '#ef4444' }}>{diceCount}</span>
                      </div>
                      <div className="move-slider-container">
                        <input
                          type="range"
                          min="1"
                          max={selectedTerritory!.units - 1}
                          value={diceCount}
                          onChange={(e) => setDiceCount(parseInt(e.target.value))}
                          className="move-slider attack-slider"
                        />
                        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.6rem', color: 'var(--text-muted)' }}>
                          <span>1</span>
                          <span style={{ color: '#94a3b8' }}>🎲 {Math.min(diceCount, 3)} dice rolled</span>
                          <span>Max ({selectedTerritory!.units - 1})</span>
                        </div>
                      </div>
                      <button
                        className="btn-primary"
                        style={{ background: '#ef4444' }}
                        disabled={selectedTerritory!.units <= 1 || !gameState.is_human_turn}
                        onClick={() => handleAction('attack', {
                          attacker: selectedTerritory!.name,
                          defender: targetTerritory.name,
                          attacker_count: diceCount
                        })}
                      >
                        <Swords size={16} /> Launch Attack ({diceCount} units)
                      </button>
                    </div>
                  )}

                  {gameState.phase === 'MOVE' && selectedTerritory?.owner === gameState.current_player && targetTerritory?.owner === gameState.current_player && (
                    <div className="move-selector">
                      <div className="move-count-display">
                        <p className="label">Units to move:</p>
                        <span className="move-value">{moveCount}</span>
                      </div>
                      <div className="move-slider-container">
                        <input
                          type="range"
                          min="1"
                          max={selectedTerritory!.units - 1}
                          value={moveCount}
                          onChange={(e) => setMoveCount(parseInt(e.target.value))}
                          className="move-slider"
                        />
                        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.6rem', color: 'var(--text-muted)' }}>
                          <span>1</span>
                          <span>Max ({selectedTerritory!.units - 1})</span>
                        </div>
                      </div>
                      <button
                        className="btn-primary"
                        disabled={!gameState.is_human_turn}
                        onClick={() => handleAction('fortify', {
                          from_territory: selectedTerritory!.name,
                          to_territory: targetTerritory!.name,
                          count: moveCount
                        })}
                      >
                        <ArrowRight size={16} /> Confirm Move
                      </button>
                    </div>
                  )}
                </div>

                <div className="panel-footer" style={{ marginTop: '1rem' }}>
                  <p className="label-tiny">Adjacent Frontlines</p>
                  <div className="tag-container">
                    {(targetTerritory || selectedTerritory)?.adjacent.map(adj => (
                      <span key={adj} className="tag">{adj}</span>
                    ))}
                  </div>
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </main>

      {/* Batch Creation Modal */}
      <AnimatePresence>
        {showBatchModal && (
          <div className="modal-overlay">
            <motion.div
              initial={{ opacity: 0, scale: 0.9 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.9 }}
              className="glass-panel modal-content"
            >
              <h2 className="panel-title" style={{ marginBottom: '1.5rem' }}>Start New Batch</h2>
              <div className="panel-stats" style={{ display: 'block' }}>
                <div style={{ display: 'flex', gap: '1rem', marginBottom: '1rem' }}>
                  <div style={{ flex: 1 }}>
                    <span className="label">Simulations in Batch</span>
                    <input
                      type="number"
                      value={batchConfig.count}
                      onChange={e => setBatchConfig({ ...batchConfig, count: parseInt(e.target.value) })}
                      className="sim-input"
                    />
                  </div>
                  <div style={{ flex: 1 }}>
                    <span className="label">Players</span>
                    <input
                      type="number"
                      max="6" min="2"
                      value={batchConfig.players.length}
                      onChange={e => {
                        const newCount = parseInt(e.target.value);
                        if (isNaN(newCount) || newCount < 2 || newCount > 6) return;

                        setBatchConfig(prev => {
                          const newPlayers = [...prev.players];
                          if (newCount > newPlayers.length) {
                            for (let i = newPlayers.length; i < newCount; i++) {
                              newPlayers.push({ name: defaultPlayerNames[i], agent_type: 'human' });
                            }
                          } else if (newCount < newPlayers.length) {
                            newPlayers.splice(newCount);
                          }
                          return { ...prev, players: newPlayers };
                        });
                      }}
                      className="sim-input"
                    />
                  </div>
                </div>

                {/* Auto-Scoring Toggle */}
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '0.75rem', borderRadius: '8px', background: batchConfig.scoring ? 'rgba(16,185,129,0.08)' : 'rgba(255,255,255,0.03)', border: `1px solid ${batchConfig.scoring ? 'rgba(16,185,129,0.3)' : 'var(--glass-border)'}`, marginBottom: '1rem', transition: 'all 0.3s' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
                    <Activity size={15} style={{ color: batchConfig.scoring ? '#10b981' : 'var(--text-muted)', flexShrink: 0 }} />
                    <div>
                      <div style={{ fontSize: '0.85rem', fontWeight: 600, color: batchConfig.scoring ? '#e2e8f0' : 'var(--text-muted)' }}>Auto-Scoring</div>
                      <div style={{ fontSize: '0.65rem', color: 'var(--text-muted)', marginTop: '0.1rem' }}>Score agents each turn and inject coaching into prompts</div>
                    </div>
                  </div>
                  <label className="train-toggle">
                    <input
                      type="checkbox"
                      checked={batchConfig.scoring}
                      onChange={e => setBatchConfig({ ...batchConfig, scoring: e.target.checked })}
                    />
                    <span className="train-toggle-slider" />
                  </label>
                </div>

                <div className="player-config-list" style={{ borderTop: '1px solid var(--glass-border)', paddingTop: '1rem' }}>
                  <span className="label">Player Agents</span>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem', marginTop: '0.5rem' }}>
                    {batchConfig.players.map((p, idx) => (
                      <div key={idx} style={{ display: 'flex', gap: '1rem', alignItems: 'center' }}>
                        <span style={{ minWidth: '120px', fontSize: '0.9rem' }}>{p.name}</span>
                        <select
                          className="sim-select"
                          value={p.agent_type}
                          onChange={(e) => {
                            const newPlayers = [...batchConfig.players];
                            newPlayers[idx].agent_type = e.target.value;
                            setBatchConfig({ ...batchConfig, players: newPlayers });
                          }}
                        >
                          <option value="human">Human</option>
                          <option value="base">Base AI</option>
                          <option value="crew">CrewAI Faction</option>
                        </select>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
              <div className="action-bar" style={{ flexDirection: 'row', marginTop: '1rem' }}>
                {simulationId && <button className="btn-secondary" onClick={() => setShowBatchModal(false)}>Cancel</button>}
                <button className="btn-primary" onClick={handleCreateBatch} style={{ flex: 1 }}>Create Simulation</button>
              </div>
            </motion.div>
          </div>
        )}
      </AnimatePresence>
    </div>
  )
}

export default App
