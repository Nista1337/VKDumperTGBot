from aiogram.dispatcher.filters.state import State, StatesGroup


# FSM states
class States(StatesGroup):
    main = State()
    token_lvl1 = State()
    token_lvl2 = State()
    types = State()