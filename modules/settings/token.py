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


@dp.callback_query_handler(lambda c: c.data == 'token', state=States.main)
async def set_token_lvl1(call: CallbackQuery):
    await call.answer()
    token = await db.session.execute(select(User.token).filter_by(id=call.from_user.id))
    token = token.scalar_one()
    keyboard = InlineKeyboardMarkup().add(
        InlineKeyboardButton('Да', callback_data='yes'),
        InlineKeyboardButton('Нет', callback_data='back')
    )
    await States.token_lvl1.set()
    await call.message.edit_text(f'Ваш текущий токен:\n<code>{token}</code>\nХотите поменять его?',
                                 reply_markup=keyboard, parse_mode='HTML')


@dp.callback_query_handler(lambda c: c.data == 'yes', state=States.token_lvl1)
async def set_token_lvl2(call: CallbackQuery):
    await call.answer()
    await call.message.edit_text('Получите токен API по инструкции ниже\n'
                                 'https://telegra.ph/Poluchenie-klyucha-tokena-API-07-25\n'
                                 'Позже отправьте его мне')
    await States.token_lvl2.set()


@dp.message_handler(state=States.token_lvl2)
async def set_token_lvl3(message: Message, state: FSMContext):
    if 'https' in message.text:
        token = message.text.removeprefix('https://api.vk.com/blank.html#access_token=')
        token = token[:-(len(token) - 85)]
    elif len(message.text) == 85:
        token = message.text
    else:
        await message.reply('Неверный токен!\n'
                            'Попробуйте еще раз\n'
                            '(Не совпадает длина)')
        return

    await db.session.execute(update(User).filter_by(id=message.from_user.id).values(token=token))
    await db.session.commit()
    async with state.proxy() as data:
        await data['current_msg'].edit_text('Я запомню!')
        await asyncio.sleep(2)
        await back(message=data['current_msg'], from_user=message.from_user.id)
