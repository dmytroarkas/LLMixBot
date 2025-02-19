<<<<<<< HEAD
import os
import asyncio
import httpx
import re
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, CallbackQueryHandler, MessageHandler, filters
from dotenv import load_dotenv
from openai import AsyncOpenAI
from anthropic import Anthropic

# Загрузка переменных окружения
load_dotenv()

# Получение токена Telegram и API ключей
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
ANTHROPIC_API_KEY = os.getenv('ANTHROPIC_API_KEY')
XAI_API_KEY = os.getenv('XAI_API_KEY')
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')

# Глобальные переменные для хранения состояний
user_roles = {}  # формат: {chat_id: {'role_name': {'description': '...', 'llm': '...', 'max_tokens': int, 'temperature': float}}}
interaction_history = {}  # формат: {chat_id: [{'role': 'role_name', 'message': 'text'}]}
chat_tasks = {}  # формат: {chat_id: task}

# Доступные LLM
AVAILABLE_LLM = ['OpenAI', 'Anthropic', 'xAI', 'Gemini']

# Глобальный словарь для хранения уникальных идентификаторов ролей
role_ids = {}  # формат: {chat_id: {role_name: unique_id}}

def generate_unique_id(chat_id):
    """Генерирует уникальный идентификатор для роли в данном чате."""
    if chat_id not in role_ids:
        role_ids[chat_id] = {}
    existing_ids = set(role_ids[chat_id].values())
    new_id = 0
    while new_id in existing_ids:
        new_id += 1
    return new_id

WELCOME_MESSAGE = """
Добро пожаловать в бота для настройки ролей!

Доступные команды:
/start - Показать это приветственное сообщение
/addrole - Добавить новую роль
/viewroles - Просмотреть текущие настройки ролей
/startdialog - Запустить диалог ролей
/stop - Остановить текущий диалог
/clearroles - Очистить все настроенные роли
/editrole - Редактировать описание роли
/deleterole - Удалить существующую роль

Используйте эти команды для управления ролями и их взаимодействием.
"""

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_roles[chat_id] = {}
    interaction_history[chat_id] = []
    await update.message.reply_text(WELCOME_MESSAGE)

async def add_role(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    await update.message.reply_text("Введите название новой роли:")
    context.user_data['awaiting_role_name'] = True

async def edit_role(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if chat_id not in user_roles or not user_roles[chat_id]:
        await update.message.reply_text("Нет настроенных ролей для редактирования. Используйте /addrole для добавления.")
        return

    # Создаем кнопки для выбора роли
    role_names = list(user_roles[chat_id].keys())
    keyboard = [
        [InlineKeyboardButton(role_name, callback_data=f"edit_{i}")] for i, role_name in enumerate(role_names)
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Выберите роль, которую хотите отредактировать:", reply_markup=reply_markup)

=======
>>>>>>> 401afa9c907c24aa76d2dd278cfc0e112dd5cf24
async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    message_text = update.message.text

    if context.user_data.get('awaiting_role_name'):
        role_name = message_text
        unique_id = generate_unique_id(chat_id)
        role_ids[chat_id][role_name] = unique_id
        context.user_data['role_name'] = role_name
        context.user_data['awaiting_role_name'] = False
        await update.message.reply_text("Введите описание (промпт) для роли:")
        context.user_data['awaiting_role_description'] = True
        return

    if context.user_data.get('awaiting_role_description'):
        role_name = context.user_data['role_name']
        user_roles[chat_id][role_name] = {'description': message_text, 'llm': None, 'max_tokens': 1000, 'temperature': 0.7}
        context.user_data['awaiting_role_description'] = False
        await update.message.reply_text("Выберите модель LLM для роли:")
        keyboard = [
            [InlineKeyboardButton(llm, callback_data=f"assign_{role_name}_{llm}") for llm in AVAILABLE_LLM]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("Выберите LLM:", reply_markup=reply_markup)
        return

    if context.user_data.get('awaiting_edit_role_name'):
        role_name = message_text
        if role_name in user_roles[chat_id]:
            context.user_data['edit_role_name'] = role_name
            context.user_data['awaiting_edit_role_name'] = False
            await update.message.reply_text("Введите новое описание для роли:")
            context.user_data['awaiting_new_role_description'] = True
        else:
            await update.message.reply_text("Роль не найдена. Пожалуйста, введите корректное название роли.")
        return

    if context.user_data.get('awaiting_new_role_description'):
        role_name = context.user_data['edit_role_name']
        user_roles[chat_id][role_name]['description'] = message_text
        context.user_data['awaiting_new_role_description'] = False
        await update.message.reply_text(f"Описание для роли {role_name} обновлено.")
        return

    await update.message.reply_text("Используйте /addrole для добавления новой роли.")

async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    try:
        if query.data.startswith('assign_'):
<<<<<<< HEAD
            _, role_id_str, llm = query.data.split('_')
            chat_id = query.message.chat_id

            # Поиск имени роли по уникальному идентификатору
            role_name = next((name for name, id in role_ids[chat_id].items() if str(id) == role_id_str), None)
            if role_name is None:
=======
            parts = query.data.split('_')
            if len(parts) != 3:
                await query.message.reply_text("Ошибка: неверный формат данных кнопки.")
                return

            _, role_name, llm = parts

            chat_id = query.message.chat_id

            if role_name not in user_roles[chat_id]:
>>>>>>> 401afa9c907c24aa76d2dd278cfc0e112dd5cf24
                await query.message.reply_text("Ошибка: роль не найдена.")
                return

            user_roles[chat_id][role_name]['llm'] = llm
            await query.message.reply_text(f"Роль {role_name} назначена на {llm}.")
            await query.message.edit_reply_markup(reply_markup=None)

        elif query.data.startswith('edit_'):
            _, role_index = query.data.split('_')
            chat_id = query.message.chat_id
            role_names = list(user_roles[chat_id].keys())
            role_name = role_names[int(role_index)]
            context.user_data['edit_role_name'] = role_name
            await query.message.reply_text("Введите новое описание для роли:")
            context.user_data['awaiting_new_role_description'] = True
            await query.message.edit_reply_markup(reply_markup=None)

        elif query.data.startswith('delete_'):
            _, role_index = query.data.split('_')
            chat_id = query.message.chat_id
            role_names = list(user_roles[chat_id].keys())
            role_name = role_names[int(role_index)]
            del user_roles[chat_id][role_name]
            await query.message.reply_text(f"Роль {role_name} была удалена.")
            await query.message.edit_reply_markup(reply_markup=None)

    except ValueError as e:
        await query.message.reply_text(f"Ошибка обработки данных кнопки: {str(e)}")
        print(f"Ошибка обработки данных кнопки: {str(e)}")
