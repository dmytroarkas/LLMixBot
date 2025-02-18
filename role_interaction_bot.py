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
user_roles = {}  # формат: {chat_id: {'role_name': {'description': '...', 'llm': '...'}}}
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

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    message_text = update.message.text

    if context.user_data.get('awaiting_role_name'):
        context.user_data['role_name'] = message_text
        context.user_data['awaiting_role_name'] = False
        await update.message.reply_text("Введите описание (промпт) для роли:")
        context.user_data['awaiting_role_description'] = True
        return

    if context.user_data.get('awaiting_role_description'):
        role_name = context.user_data['role_name']
        user_roles[chat_id][role_name] = {'description': message_text, 'llm': None}
        context.user_data['awaiting_role_description'] = False
        await update.message.reply_text("Выберите модель LLM для роли:")
        keyboard = [
            [InlineKeyboardButton(llm, callback_data=f"assign_{role_name}_{llm}") for llm in AVAILABLE_LLM]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("Выберите LLM:", reply_markup=reply_markup)
        return

    await update.message.reply_text("Используйте /addrole для добавления новой роли.")

async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data.startswith('assign_'):
        _, role_name, llm = query.data.split('_')
        chat_id = query.message.chat_id
        user_roles[chat_id][role_name]['llm'] = llm
        await query.message.reply_text(f"Роль {role_name} назначена на {llm}.")
        await query.message.edit_reply_markup(reply_markup=None)

async def view_roles(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if chat_id not in user_roles or not user_roles[chat_id]:
        await update.message.reply_text("Нет настроенных ролей. Используйте /addrole для добавления.")
        return

    roles_info = "Текущие настройки ролей:\n"
    for role_name, details in user_roles[chat_id].items():
        roles_info += f"Роль: {role_name}\nОписание: {details['description']}\nLLM: {details['llm']}\n\n"
    
    await update.message.reply_text(roles_info)

async def clear_roles(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_roles[chat_id] = {}
    await update.message.reply_text("Все роли были очищены.")

async def get_llm_response(prompt, llm, description):
    try:
        if llm == 'OpenAI':
            client = AsyncOpenAI(api_key=OPENAI_API_KEY)
            response = await client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "system", "content": description}, {"role": "user", "content": prompt}],
                max_tokens=1000,
                temperature=0.7
            )
            return response.choices[0].message.content
        elif llm == 'Anthropic':
            client = Anthropic(api_key=ANTHROPIC_API_KEY)
            message = client.messages.create(
                model="claude-3-5-sonnet-20241022",
                max_tokens=1000,
                temperature=0.7,
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
                          "model": "grok-2-vision-1212", "stream": False, "temperature": 0.9}
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
                response = await get_llm_response(prompt, details['llm'], details['description'])
                interaction_history[chat_id].append({'role': role_name, 'message': response})
                await update.message.reply_text(f"Ответ от {details['llm']} для роли {role_name}:\n{response}")
                await asyncio.sleep(2)  # Задержка между сообщениями

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
    application.add_handler(CallbackQueryHandler(button))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))

    print("🚀 Бот для настройки ролей запущен...")
    application.run_polling()

if __name__ == '__main__':
    main() 