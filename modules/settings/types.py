# Init imports
from init import dp
from init import db, User

# SQLAlchemy imports
from sqlalchemy.future import select
from sqlalchemy import update

# AIOGram imports
from aiogram.types import CallbackQuery
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# States import
from .states import States

# Utils imports
from utils import get_smile


@dp.callback_query_handler(lambda c: c.data == 'types', state=States.main)
async def types(call: CallbackQuery):
    await call.answer()
    result = await db.session.execute(select(User).filter_by(id=call.from_user.id))
    result = result.scalar_one()
    keyboard = InlineKeyboardMarkup().add(
        InlineKeyboardButton('ЛС ' + ('\u2705' if result.type_users else '\u274c'), callback_data='users_' +
                             ('y' if result.type_users else 'n')),
        InlineKeyboardButton('Беседы ' + ('\u2705' if result.type_chats else '\u274c'), callback_data='chats_' +
                             ('y' if result.type_chats else 'n')),
        InlineKeyboardButton('Группы ' + ('\u2705' if result.type_groups else '\u274c'), callback_data='groups_' +
                             ('y' if result.type_groups else 'n')),
        InlineKeyboardButton(get_smile('\u2b05\ufe0f') + ' Назад', callback_data='back')
    )
    await States.types.set()
    await call.message.edit_text('Это настройки чатов.\nЗдесь можно выбрать, каких типов чаты будут сохраняться,'
                                 'а каких нет', reply_markup=keyboard)


@dp.callback_query_handler(lambda c: 'users' in c.data, state=States.types)
async def toggle_users(call: CallbackQuery):
    if call.data.split('_')[1] == 'y':
        payload = False
    else:
        payload = True

    await db.session.execute(update(User).filter_by(id=call.from_user.id).values(type_users=payload))
    await db.session.commit()
    await types(call)


@dp.callback_query_handler(lambda c: 'chats' in c.data, state=States.types)
async def toggle_users(call: CallbackQuery):
    if call.data.split('_')[1] == 'y':
        payload = False
    else:
        payload = True

    await db.session.execute(update(User).filter_by(id=call.from_user.id).values(type_chats=payload))
    await db.session.commit()
    await types(call)


@dp.callback_query_handler(lambda c: 'groups' in c.data, state=States.types)
async def toggle_users(call: CallbackQuery):
    if call.data.split('_')[1] == 'y':
        payload = False
    else:
        payload = True

    await db.session.execute(update(User).filter_by(id=call.from_user.id).values(type_groups=payload))
    await db.session.commit()
    await types(call)
