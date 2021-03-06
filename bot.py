# AIOGram imports
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram import executor
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.dispatcher import FSMContext
from aiogram.types import InputFile
from aiogram.utils.exceptions import MessageNotModified
from sqlalchemy.ext.asyncio import AsyncSession, AsyncEngine

# SQLAlchemy imports
from sqlalchemy.future import select
from sqlalchemy import delete

# Util imports
from utils import get_smile
from utils import get_packed_dir

# Misc imports
import json
from loguru import logger
import subprocess
import asyncio
from threading import Thread

# Init imports
from init import User
from init import dp, bot, Dispatcher
from init import db

# Modules imports
import modules.settings
import modules.settings.token
import modules.settings.types
import modules.settings.limit


# FSM states
class States(StatesGroup):
    get_token = State()
    ask_send = State()
    working = State()
    reset = State()


# Global variables
process = {}
output = {}

logger.info('Telegram bot for VKParser by AlexanderBaransky')
logger.info('Ver. 0.1 Alpha')
logger.info('Starting polling...')


@dp.message_handler(commands='start')
async def start(message: Message):
    result = await db.session.execute(select(User.id).filter_by(id=message.from_user.id))
    if result.scalar_one_or_none() == message.from_user.id:
        await message.reply('Нельзя делать повторный старт!', reply=False)
        return

    await message.reply('Привет! Я бот для управления парсером ВК из Telegram!\n'
                        'Для работы необходимо получить токен API\n'
                        'Вот инструкция: https://telegra.ph/Poluchenie-klyucha-tokena-API-07-25\n'
                        'Позже отправьте его мне', reply=False)
    await States.get_token.set()


@dp.message_handler(state=States.get_token)
async def get_token(message: Message, state: FSMContext):
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

    db.session.add(User(id=message.from_user.id, token=token, limit=200, group_attachments=True,
                        type_users=True, type_chats=True, type_groups=True))
    await db.session.commit()
    await message.reply('Я запомню!')
    await state.finish()


@dp.message_handler(commands='reset')
async def reset(message: Message):
    keyboard = InlineKeyboardMarkup().add(
        InlineKeyboardButton('Да', callback_data='yes'),
        InlineKeyboardButton('Нет', callback_data='no')
    )
    await States.reset.set()
    await message.reply('Это удалит все ваши данные из БД (токен, настройки)!\n'
                        'Хотите продолжить?', reply_markup=keyboard)


@dp.callback_query_handler(lambda c: c.data == 'yes', state=States.reset)
async def apply_reset(call: CallbackQuery, state: FSMContext):
    await db.session.execute(delete(User).filter_by(id=call.from_user.id))
    await db.session.commit()
    await state.finish()
    await call.message.edit_text('<b>Сброс выполнен!</b>', parse_mode='HTML')
    await asyncio.sleep(3)
    await call.message.delete()


@dp.callback_query_handler(lambda c: c.data == 'no', state=States.reset)
async def cancel_reset(call: CallbackQuery, state: FSMContext):
    await call.message.delete()
    await state.finish()


async def update_status(msg: Message, user_id: int):
    global output
    output[user_id] = []
    while True:
        if process[user_id].poll() is not None:
            return process[user_id].poll()

        if output[user_id] and process[user_id].poll() is None:
            data = json.loads(output[user_id][-1])
            try:
                await bot.edit_message_text('<b>Парсер работает...</b>\n' +
                                            get_smile("\ud83d\udce9") + f' Чатов сохранено: <i>{data["current"] - 1} '
                                                                        f'из {data["total"]}</i>\n'
                                                                        f'\u274c Ошибок: <i>{data["errors"]}</i>',
                                            message_id=msg.message_id,
                                            chat_id=msg.chat.id, parse_mode='HTML')
            except MessageNotModified:
                await asyncio.sleep(0.5)
                continue

            await asyncio.sleep(3)
        else:
            await asyncio.sleep(0.5)


def update_output(user_id: int):
    global output
    for line in process[user_id].stdout:
        output[user_id].append(line.removesuffix('\n'))


@dp.message_handler(commands='launch')
async def launch(message: Message, state: FSMContext):
    await States.working.set()
    msg = await message.reply('<b>Запускаю парсер...</b>', reply=False, parse_mode='HTML')

    global process
    cmd = ['python3', 'main.py', '-j']
    user = await db.session.execute(select(User).filter_by(id=message.from_user.id))
    user = user.scalar_one()

    cmd.extend(['-t', user.token,
                '-l', str(user.limit)])
    if user.type_users:
        cmd.append('-u')

    if user.type_chats:
        cmd.append('-c')

    if user.type_groups:
        cmd.append('-g')

    if user.group_attachments:
        cmd.append('-G')

    process[message.from_user.id] = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                                     text=True, cwd='../')
    await bot.edit_message_text('<b>Парсер запущен!</b>', chat_id=message.chat.id, message_id=msg.message_id,
                                parse_mode='HTML')

    Thread(target=update_output, args=(message.from_user.id,), daemon=True).start()
    code = await update_status(msg, message.from_user.id)
    await state.finish()
    keyboard = None
    if code == 0:
        text = '\u2705 <b>Завершено!</b>\nСохранение выполнено'
    elif code == -15:
        text = get_smile("\ud83d\udfe8") + ' <b>Завершено!</b>\nПарсер завершен вручную\n' \
                                           'Сохранение выполнено частично\nОтправить архив?'
        keyboard = InlineKeyboardMarkup().add(
            InlineKeyboardButton('Да', callback_data='yes'),
            InlineKeyboardButton('Нет', callback_data='no')
        )
        await States.ask_send.set()
    elif code == 100:
        await bot.edit_message_text('\u274c <b>Ошибка!</b>\nНеверный токен!', message_id=msg.message_id,
                                    chat_id=msg.chat.id, parse_mode='HTML')
        return
    else:
        await bot.edit_message_text(f'\u274c <b>Неизвестная ошибка!</b>\nКод выхода: {code}', message_id=msg.message_id,
                                    chat_id=msg.chat.id, parse_mode='HTML')
        return

    if keyboard:
        await bot.edit_message_text(text, message_id=msg.message_id,
                                    chat_id=msg.chat.id, parse_mode='HTML', reply_markup=keyboard)
        return
    else:
        await bot.edit_message_text(text, message_id=msg.message_id,
                                    chat_id=msg.chat.id, parse_mode='HTML')

    await send_wrapper(message=msg, user_id=message.from_user.id)


@dp.message_handler(commands='stop', state=States.working)
async def stop(message: Message):
    msg = await message.reply('<b>Останавливаю парсер...</b>', reply=False, parse_mode='HTML')
    process[message.from_user.id].terminate()
    await bot.edit_message_text('<b>Парсер остановлен!</b>', message_id=msg.message_id, chat_id=msg.chat.id,
                                parse_mode='HTML')
    await asyncio.sleep(3)
    await msg.delete()


@dp.callback_query_handler(lambda c: c.data == 'yes', state=States.ask_send)
async def send_wrapper(call: CallbackQuery = None, message: Message = None, user_id: int = None,
                       state: FSMContext = None):
    if state:
        await state.finish()

    data = json.loads(output[user_id][-1])
    if message:
        msg = message
    else:
        msg = call.message

    bot_msg = await msg.reply('<b>Отправляю архив...</b>', parse_mode='HTML', reply=False)
    await bot.send_chat_action(chat_id=msg.chat.id, action='upload_document')
    await bot.send_document(chat_id=msg.chat.id, document=InputFile(await get_packed_dir('../' + data['path'][:-1])))
    await bot_msg.edit_text('<b>Готово!</b>', parse_mode='HTML')


@dp.callback_query_handler(lambda c: c.data == 'no', state=States.ask_send)
async def reset_keyboard(call: CallbackQuery, state: FSMContext):
    await state.finish()
    await bot.edit_message_text(text=get_smile("\ud83d\udfe8") + ' <b>Завершено!</b>\nПарсер завершен вручную\n'
                                                                 'Сохранение выполнено частично',
                                message_id=call.message.message_id, chat_id=call.message.chat.id, parse_mode='HTML')


async def on_startup(dp: Dispatcher):
    await db.init_db()
    logger.info('Started OK')


async def on_shutdown(dp: Dispatcher):
    await db.session.close()
    await db.engine.dispose()


executor.start_polling(dp, on_startup=on_startup, on_shutdown=on_shutdown)
