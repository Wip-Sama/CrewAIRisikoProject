from enum import Enum, auto

class GamePhase(Enum):
    INIT = auto()
    INITIAL_PLACEMENT = auto()
    ASSIGN_STD_ARMIES = auto()
    ASK_FOR_CARDS = auto()
    PLACE_ARMIES = auto()
    BATTLE = auto()
    WAR = auto()
    CONQUER = auto()
    MOVE = auto()
    DRAW_CARD = auto()
    ENDGAME = auto()

class UnitType(Enum):
    CANNONE = 0
    FANTE = 1
    CAVALLO = 2
    JOLLY = 3

# UI Constants (legacy, might be refactored later)
phase_button = [(50, 720), (300, 830)]
phase_text = (100, 785)