# AIOGram imports
from aiogram import Bot, Dispatcher, executor
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.dispatcher import FSMContext
from aiogram.types import InputFile

from aiogram.utils.exceptions import MessageNotModified

# SQLAlchemy imports
from sqlalchemy import Column
from sqlalchemy import Integer, String, Boolean
from sqlalchemy.ext.asyncio import AsyncSession, AsyncEngine
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.future import select
from sqlalchemy import delete
from sqlalchemy.orm import declarative_base, sessionmaker

# Misc imports
import os
import json
from loguru import logger
import subprocess
import asyncio
from threading import Thread

from zipstream import AioZipStream
import aiofiles

logger.info('Telegram bot for VKParser by AlexanderBaransky')
logger.info('Ver. 0.0.5')

# Config loading
with open('telegram/config.json') as f:
    config = json.load(f)

with open('config.json') as f:
    parser_config = json.load(f)

# AIOGram initialization
storage = MemoryStorage()
bot = Bot(config['token'])
dp = Dispatcher(bot, storage=storage)

# SQLAlchemy initialization
Base = declarative_base()


class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True)
    token = Column(String, nullable=False)
    limit = Column(Integer, nullable=False)
    group_attachments = Column(Boolean, nullable=False)
    type_users = Column(Boolean, nullable=False)
    type_chats = Column(Boolean, nullable=False)
    type_groups = Column(Boolean, nullable=False)


async def init_db():
    global db_engine
    db_engine = create_async_engine("sqlite+aiosqlite:///db.sqlite", )

    async with db_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async_session = sessionmaker(db_engine, class_=AsyncSession)
    global db_session
    db_session = async_session()
    await db_session.begin()


# FSM states
class States(StatesGroup):
    get_token = State()
    ask_send = State()
    working = State()
    reset = State()


process: subprocess.Popen
stdout_worker: Thread
output = []
db_session: AsyncSession
db_engine: AsyncEngine

logger.info('Starting polling...')


def update_parser_config():
    f = open('config.json', 'w')
    json.dump(parser_config, f)


@dp.message_handler(commands='start')
async def start(message: Message):
    result = await db_session.execute(select(User.id).filter_by(id=message.from_user.id))
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
        await message.reply('Я запомню!')
        await state.finish()
    elif len(message.text) == 85:
        token = message.text
        await message.reply('Я запомню!')
        await state.finish()
    else:
        await message.reply('Неверный токен!\n'
                            'Попробуйте еще раз\n'
                            '(Не совпадает длина)')
        return

    db_session.add(User(id=message.from_user.id, token=token, limit=200, group_attachments=True,
                        type_users=True, type_chats=True, type_groups=True))
    await db_session.commit()


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
    await db_session.execute(delete(User).filter_by(id=call.from_user.id))
    await db_session.commit()
    await state.finish()
    await call.message.edit_text('<b>Сброс выполнен!</b>', parse_mode='HTML')
    await asyncio.sleep(3)
    await call.message.delete()


@dp.callback_query_handler(lambda c: c.data == 'no', state=States.reset)
async def cancel_reset(call: CallbackQuery, state: FSMContext):
    await call.message.delete()
    await state.finish()


async def update_status(msg: Message):
    while True:
        if process.poll() is not None:
            return process.poll()

        if output and process.poll() is None:
            data = json.loads(output[-1])
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


def update_output():
    global output
    for line in process.stdout:
        output.append(line.removesuffix('\n'))


def get_smile(text: str):
    return text.encode('utf-16', 'surrogatepass').decode('utf-16')


async def pack_upload(msg: Message, dir_name: str):
    await bot.edit_message_text('<b>Отправляю архив...</b>', message_id=msg.message_id,
                                chat_id=msg.chat.id, parse_mode='HTML')
    await bot.send_chat_action(chat_id=msg.chat.id, action='upload_document')
    files = []
    for folder_name, subfolders, filenames in os.walk(dir_name):
        for filename in filenames:
            # create complete filepath of file in directory
            file_path = os.path.join(folder_name, filename)
            # Add file to zip
            files.append({'file': file_path,
                          'name': os.path.relpath(file_path,
                                                  os.path.join(dir_name, '..'))})

    if not os.path.exists('packed'):
        os.makedirs('packed')

    aiozip = AioZipStream(files)
    zip_filename = 'packed/' + dir_name + '.zip'
    zip_file = await aiofiles.open(zip_filename, 'wb')
    async for chunk in aiozip.stream():
        await zip_file.write(chunk)

    await zip_file.close()

    await bot.send_document(chat_id=msg.chat.id, document=InputFile(zip_filename))
    await bot.edit_message_text('<b>Готово!</b>', message_id=msg.message_id,
                                chat_id=msg.chat.id, parse_mode='HTML')


@dp.message_handler(commands='launch')
async def launch(message: Message, state: FSMContext):
    await States.working.set()
    msg = await message.reply('<b>Запускаю парсер...</b>', reply=False, parse_mode='HTML')

    global process
    cmd = ['python3', 'main.py', '-j']
    user = await db_session.execute(select(User).filter_by(id=message.from_user.id))
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

    process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    await bot.edit_message_text('<b>Парсер запущен!</b>', chat_id=message.chat.id, message_id=msg.message_id,
                                parse_mode='HTML')

    global stdout_worker
    global output

    stdout_worker = Thread(target=update_output, daemon=True).start()
    code = await update_status(msg)
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

    await asyncio.sleep(2)
    await send_wrapper(message=msg)


@dp.message_handler(commands='stop')
async def stop(message: Message):
    msg = await message.reply('<b>Останавливаю парсер...</b>', reply=False, parse_mode='HTML')
    process.terminate()
    await bot.edit_message_text('<b>Парсер остановлен!</b>', message_id=msg.message_id, chat_id=msg.chat.id,
                                parse_mode='HTML')
    await asyncio.sleep(3)
    await msg.delete()


@dp.callback_query_handler(lambda c: c.data == 'yes', state=States.ask_send)
async def send_wrapper(call: CallbackQuery = None, message: Message = None, state: FSMContext = None):
    if state:
        await state.finish()

    global output
    data = json.loads(output[-1])
    if message:
        await pack_upload(message, data['path'][:-1])
    else:
        await pack_upload(call.message, data['path'][:-1])
    output = []


@dp.callback_query_handler(lambda c: c.data == 'no', state=States.ask_send)
async def reset_keyboard(call: CallbackQuery, state: FSMContext):
    await state.finish()
    await bot.edit_message_text(text=get_smile("\ud83d\udfe8") + ' <b>Завершено!</b>\nПарсер завершен вручную\n'
                                                                 'Сохранение выполнено частично',
                                message_id=call.message.message_id, chat_id=call.message.chat.id, parse_mode='HTML')
    global output
    output = []


async def on_startup(dp: Dispatcher):
    await init_db()
    logger.info('Started OK')


async def on_shutdown(dp: Dispatcher):
    await db_engine.dispose()


executor.start_polling(dp, on_startup=on_startup, on_shutdown=on_shutdown)
