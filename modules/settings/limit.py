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

# Misc imports
import asyncio
from .settings import back


@dp.callback_query_handler(lambda c: c.data == 'limit', state=States.main)
async def set_limit_lvl1(call: CallbackQuery):
    await call.answer()
    limit = await db.session.execute(select(User.limit).filter_by(id=call.from_user.id))
    limit = limit.scalar_one()
    if limit == 0:
        limit = 'Нет лимита'
    keyboard = InlineKeyboardMarkup().add(
        InlineKeyboardButton('Да', callback_data='yes'),
        InlineKeyboardButton('Нет', callback_data='back')
    )
    await States.limit_lvl1.set()
    await call.message.edit_text('Здесь можно настроить максимальное количество сообщений которое будет сохранено из '
                                 f'каждого чата\nТекущий лимит: <code>{limit}</code>\nХотите поменять его?',
                                 parse_mode='HTML', reply_markup=keyboard)


@dp.callback_query_handler(lambda c: c.data == 'yes', state=States.limit_lvl1)
async def set_limit_lvl2(call: CallbackQuery):
    await call.answer()
    await call.message.edit_text('Хорошо, отправьте максимальное количество сообщений для каждого чата\n'
                                 'Лимит не может быть меньше 200, если вы хотите отключить лимит '
                                 '(сохранять чаты полностью), отправьте 0')
    await States.limit_lvl2.set()


@dp.message_handler(state=States.limit_lvl2)
async def set_limit_lvl3(message: Message, state: FSMContext):
    limit = message.text
    if limit.isdigit() and (int(limit) >= 200 or int(limit) == 0):
        await db.session.execute(update(User).filter_by(id=message.from_user.id).values(limit=limit))
        await db.session.commit()
        async with state.proxy() as data:
            await data['current_msg'].edit_text('Я запомню!')
            await asyncio.sleep(2)
            await back(message=data['current_msg'], from_user=message.from_user.id)
