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

    # Ожидаем следующего сообщения от пользователя
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

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    message_text = update.message.text

    # Инициализация записи для chat_id, если она отсутствует
    if chat_id not in user_roles:
        user_roles[chat_id] = {}

    if context.user_data.get('awaiting_role_name'):
        context.user_data['role_name'] = message_text
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
            [InlineKeyboardButton(llm, callback_data=f"assign_{role_name[:10]}_{llm[:10]}") for llm in AVAILABLE_LLM]
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
    
    if query.data.startswith('assign_'):
        _, role_index, llm = query.data.split('_')
        chat_id = query.message.chat_id
        role_names = list(user_roles[chat_id].keys())
        role_name = role_names[int(role_index)]
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

async def view_roles(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if chat_id not in user_roles or not user_roles[chat_id]:
        await update.message.reply_text("Нет настроенных ролей. Используйте /addrole для добавления.")
        return

    roles_info = "Текущие настройки ролей:\n"
    for role_name, details in user_roles[chat_id].items():
        roles_info += (f"Роль: {role_name}\nОписание: {details['description']}\n"
                       f"LLM: {details['llm']}\nМакс. длина: {details['max_tokens']}\n"
                       f"Температура: {details['temperature']}\n\n")
    
    await update.message.reply_text(roles_info)

async def clear_roles(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_roles[chat_id] = {}
    await update.message.reply_text("Все роли были очищены.")

async def get_llm_response(prompt, llm, description, max_tokens, temperature):
    try:
        if llm == 'OpenAI':
            client = AsyncOpenAI(api_key=OPENAI_API_KEY)
            response = await client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "system", "content": description}, {"role": "user", "content": prompt}],
                max_tokens=max_tokens,
                temperature=temperature
            )
            return response.choices[0].message.content
        elif llm == 'Anthropic':
            client = Anthropic(api_key=ANTHROPIC_API_KEY)
            message = client.messages.create(
                model="claude-3-5-sonnet-20241022",
                max_tokens=max_tokens,
                temperature=temperature,
                system=description,
                messages=[{"role": "user", "content": prompt}]
            )
            return message.content if isinstance(message.content, str) else message.content[0].text
        elif llm == 'xAI':
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    "https://api.x.ai/v1/chat/completions",
                    headers={"Content-Type": "application/json", "Authorization": f"Bearer {XAI_API_KEY}"},
                    json={"messages": [{"role": "system", "content": description}, {"role": "user", "content": prompt}],
                          "model": "grok-2-vision-1212", "stream": False, "temperature": temperature}
                )
                response_data = response.json()
                return re.sub(r'\*\*', '', response_data['choices'][0]['message']['content'])
        elif llm == 'Gemini':
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}",
                    headers={"Content-Type": "application/json"},
                    json={"contents": [{"parts": [{"text": description}, {"text": prompt}]}]}
                )
                response_data = response.json()
                if 'error' in response_data:
                    return f"Ошибка API: {response_data['error']['message']}"
                content = response_data['candidates'][0]['content']['parts'][0]['text']
                return re.sub(r'\*\*', '', re.sub(r'\n{3,}', '\n\n', content))
    except Exception as e:
        return f"Ошибка: {str(e)}"

async def start_dialog(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if chat_id in chat_tasks:
        await update.message.reply_text("Диалог уже запущен. Используйте /stop для остановки.")
        return

    if not user_roles.get(chat_id):
        await update.message.reply_text("Нет настроенных ролей. Используйте /addrole для добавления.")
        return

    async def dialog_loop():
        while True:
            for role_name, details in user_roles[chat_id].items():
                # Формируем контекст из последних сообщений
                context_messages = "\n".join(
                    [f"{entry['role']}: {entry['message']}" for entry in interaction_history[chat_id][-5:]]
                )
                prompt = f"{details['description']}\nКонтекст:\n{context_messages}"
                response = await get_llm_response(prompt, details['llm'], details['description'], details['max_tokens'], details['temperature'])
                interaction_history[chat_id].append({'role': role_name, 'message': response})
                await update.message.reply_text(f"Ответ от {details['llm']} для роли {role_name}:\n{response}")
                await asyncio.sleep(3)  # Задержка в 3 секунды между сообщениями

    task = asyncio.create_task(dialog_loop())
    chat_tasks[chat_id] = task
    await update.message.reply_text("Диалог ролей запущен.")

async def stop_dialog(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if chat_id in chat_tasks:
        chat_tasks[chat_id].cancel()
        del chat_tasks[chat_id]
        await update.message.reply_text("Диалог ролей остановлен.")
    else:
        await update.message.reply_text("Нет активного диалога для остановки.")

def main():
    application = Application.builder().token(TELEGRAM_TOKEN).build()

    # Основные обработчики
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("addrole", add_role))
    application.add_handler(CommandHandler("viewroles", view_roles))
    application.add_handler(CommandHandler("startdialog", start_dialog))
    application.add_handler(CommandHandler("stop", stop_dialog))
    application.add_handler(CommandHandler("clearroles", clear_roles))
    application.add_handler(CommandHandler("editrole", edit_role))
    application.add_handler(CallbackQueryHandler(button))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))

    print("🚀 Бот для настройки ролей запущен...")
    application.run_polling()

if __name__ == '__main__':
    main() 
