# Init imports
from init import dp
from init import db, User

# SQLAlchemy imports
from sqlalchemy.future import select
from sqlalchemy import update

# AIOGram imports
from aiogram.types import Message, CallbackQuery
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.dispatcher import FSMContext

# States import
from .states import States


@dp.message_handler(commands='settings')
async def settings(message: Message, state: FSMContext):
    result = await db.session.execute(select(User.group_attachments).filter_by(id=message.from_user.id))
    result = result.scalar_one()

    msg = await show_settings(message, result)

    async with state.proxy() as data:
        data['current_msg'] = msg


async def show_settings(message: Message, result: bool, edit: bool = False):
    keyboard = InlineKeyboardMarkup(row_width=3).add(
        InlineKeyboardButton('Токен', callback_data='token'),
        InlineKeyboardButton('Типы чатов', callback_data='types'),
        InlineKeyboardButton('Лимит', callback_data='limit'),
        InlineKeyboardButton('Группировать вложения: ' + ('\u2705' if result else '\u274c'),
                             callback_data='group_attach_' + ('y' if result else 'n'))
    ).row(
        InlineKeyboardButton('\u274c' + 'Выход', callback_data='close')
    )
    await States.main.set()
    text = 'Это меню настроек. Тут можно подстроить парсер под свои предпочтения!\n' \
           'Выберите что хотите настроить:'
    if edit:
        await message.edit_text(text, reply_markup=keyboard)
    else:
        msg = await message.reply(text, reply_markup=keyboard)
        return msg


@dp.callback_query_handler(lambda c: 'group_attach' in c.data, state=States.main)
async def switch_group_attach(call: CallbackQuery):
    await call.answer()
    if call.data.split('_')[2] == 'y':
        payload = False
    else:
        payload = True

    await db.session.execute(update(User).filter_by(id=call.from_user.id).values(group_attachments=payload))
    await db.session.commit()
    await show_settings(call.message, payload, True)


@dp.callback_query_handler(lambda c: c.data == 'back', state=States)
async def back(call: CallbackQuery = None, message: Message = None, from_user: int = None):
    if call:
        await call.answer()
        result = await db.session.execute(select(User.group_attachments).filter_by(id=call.from_user.id))
        result = result.scalar_one()
        await show_settings(call.message, result, True)
    else:
        result = await db.session.execute(select(User.group_attachments).filter_by(id=from_user))
        result = result.scalar_one()
        await show_settings(message, result, True)


@dp.callback_query_handler(lambda c: c.data == 'close', state=States)
async def close(call: CallbackQuery, state: FSMContext):
    await call.message.delete()
    await state.finish()
