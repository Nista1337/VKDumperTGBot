# AIOGram imports
from aiogram import Bot, Dispatcher, executor
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.dispatcher import FSMContext
from aiogram.types import InputFile

from aiogram.utils.exceptions import MessageNotModified

import os
import json
from loguru import logger
import subprocess
import asyncio
from threading import Thread

from zipstream import AioZipStream
import aiofiles

logger.info('Telegram bot for VKParser by AlexanderBaransky')
logger.info('Ver. 0.0.4')

# Config loading
with open('telegram/config.json') as f:
    config = json.load(f)

with open('config.json') as f:
    parser_config = json.load(f)

# AIOGram initialization
storage = MemoryStorage()
bot = Bot(config['token'])
dp = Dispatcher(bot, storage=storage)


# FSM states
class States(StatesGroup):
    get_token = State()
    ask_send = State()


process: subprocess.Popen
stdout_worker: Thread
output = []

logger.info('Starting polling...')


def update_parser_config():
    f = open('config.json', 'w')
    json.dump(parser_config, f)


@dp.message_handler(commands='start')
async def start(message: Message):
    await message.reply('Привет! Я бот для управления парсером ВК из Telegram!\n'
                        'Для работы необходимо получить токен API\n'
                        'Вот инструкция: https://telegra.ph/Poluchenie-klyucha-tokena-API-07-25\n'
                        'Позже отправьте его мне')
    await States.get_token.set()


@dp.message_handler(state=States.get_token)
async def get_token(message: Message, state: FSMContext):
    if 'https' in message.text:
        token = message.text.removeprefix('https://api.vk.com/blank.html#access_token=')
        token = token[:-(len(token) - 85)]
        parser_config['token'] = token
        update_parser_config()
        await message.reply('Я запомню!')
        await state.finish()
    elif len(message.text) == 85:
        parser_config['token'] = message.text
        update_parser_config()
        await message.reply('Я запомню!')
        await state.finish()
    else:
        await message.reply('Неверный токен!\n'
                            'Попробуйте еще раз\n'
                            '(Не совпадает длина)')


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
                                            f'\u274c Ошибок: <i>{data["errors"]}</i>', message_id=msg.message_id,
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
async def launch(message: Message):
    msg = await message.reply('<b>Запускаю парсер...</b>', reply=False, parse_mode='HTML')
    global process
    process = subprocess.Popen(['python3', 'main.py', '-j'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    await bot.edit_message_text('<b>Парсер запущен!</b>', chat_id=message.chat.id, message_id=msg.message_id, parse_mode='HTML')

    global stdout_worker
    global output

    stdout_worker = Thread(target=update_output, daemon=True).start()
    code = await update_status(msg)
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


@dp.message_handler()
async def lol(message: Message):
    await message.reply(message.text)


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
    logger.info('Started OK')


executor.start_polling(dp, on_startup=on_startup)
