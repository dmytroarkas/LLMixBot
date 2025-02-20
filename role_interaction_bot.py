import os
import asyncio
import httpx
import re
import uuid
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
user_roles = {}  # формат: {chat_id: {role_id: {'name': 'role_name', 'description': '...', 'llm': '...', 'max_tokens': int, 'temperature': float}}}
role_ids = {}  # формат: {chat_id: {role_name: role_id}}
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
/deleterole - Удалить существующую роль

Используйте эти команды для управления ролями и их взаимодействием.

Помните, что начало и поддержка диалога зависит от промптов ваших ролей. Если промпты прописаны не четко, диалог может не начаться или не поддерживаться.

Длину сообщений в диалоге можно регулировать в промптах ваших ролей.
"""

def generate_unique_role_id(chat_id, role_name):
    """Генерирует уникальный идентификатор для роли."""
    role_id = str(uuid.uuid4())
    while role_id in user_roles.get(chat_id, {}):
        role_id = str(uuid.uuid4())
    role_ids.setdefault(chat_id, {})[role_name] = role_id
    return role_id

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
    role_names = [(details['name'], role_id) for role_id, details in user_roles[chat_id].items()]
    keyboard = [
        [InlineKeyboardButton(role_name, callback_data=f"edit_{role_id}")] for role_name, role_id in role_names
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
        role_name = message_text
        role_id = generate_unique_role_id(chat_id, role_name)
        context.user_data['role_id'] = role_id
        context.user_data['role_name'] = role_name
        context.user_data['awaiting_role_name'] = False
        await update.message.reply_text("Введите описание (промпт) для роли:")
        context.user_data['awaiting_role_description'] = True
        return

    if context.user_data.get('awaiting_role_description'):
        role_id = context.user_data['role_id']
        role_name = context.user_data['role_name']
        user_roles[chat_id][role_id] = {'name': role_name, 'description': message_text, 'llm': None, 'max_tokens': 1000, 'temperature': 0.7}
        context.user_data['awaiting_role_description'] = False
        await update.message.reply_text("Выберите модель LLM для роли:")
        keyboard = [
            [InlineKeyboardButton(llm, callback_data=f"assign_{role_id}_{llm[:10]}") for llm in AVAILABLE_LLM]
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

    if context.user_data.get('awaiting_new_description'):
        role_id = context.user_data['editing_role_id']
        user_roles[chat_id][role_id]['description'] = message_text
        context.user_data['awaiting_new_description'] = False
        await update.message.reply_text("Описание роли обновлено.")
        return

    await update.message.reply_text("Используйте /addrole для добавления новой роли.")

async def delete_role(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if chat_id not in user_roles or not user_roles[chat_id]:
        await update.message.reply_text("Нет настроенных ролей для удаления. Используйте /addrole для добавления.")
        return

    # Создаем кнопки для выбора роли
    role_names = [(details['name'], role_id) for role_id, details in user_roles[chat_id].items()]
    keyboard = [
        [InlineKeyboardButton(role_name, callback_data=f"delete_{role_id}")] for role_name, role_id in role_names
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Выберите роль, которую хотите удалить:", reply_markup=reply_markup)

async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    try:
        chat_id = query.message.chat_id

        if query.data == "continue_dialog":
            await query.message.reply_text("Продолжаем обсуждение.")
            if chat_id in chat_tasks:
                chat_tasks[chat_id].cancel()
                del chat_tasks[chat_id]
            asyncio.create_task(start_dialog(update, context, from_button=True))
            await query.message.edit_reply_markup(reply_markup=None)

        elif query.data == "end_dialog":
            if chat_id in chat_tasks:
                chat_tasks[chat_id].cancel()
                del chat_tasks[chat_id]
            await query.message.reply_text("Обсуждение завершено.")
            await query.message.edit_reply_markup(reply_markup=None)

        elif query.data.startswith('assign_'):
            parts = query.data.split('_')
            if len(parts) != 3:
                await query.message.reply_text("Ошибка: неверный формат данных кнопки.")
                return

            _, role_id, llm = parts
            chat_id = query.message.chat_id

            if role_id not in user_roles[chat_id]:
                await query.message.reply_text("Ошибка: неверный идентификатор роли.")
                return

            user_roles[chat_id][role_id]['llm'] = llm
            role_name = user_roles[chat_id][role_id]['name']
            await query.message.reply_text(f"Роль {role_name} назначена на {llm}.")
            await query.message.edit_reply_markup(reply_markup=None)

        elif query.data.startswith('edit_'):
            _, role_id = query.data.split('_')
            chat_id = query.message.chat_id
            role_name = user_roles[chat_id][role_id]['name']
            context.user_data['editing_role_id'] = role_id
            await query.message.reply_text(f"Редактирование роли {role_name} начато. Введите новое описание:")
            await query.message.edit_reply_markup(reply_markup=None)
            context.user_data['awaiting_new_description'] = True

        elif query.data.startswith('delete_'):
            _, role_id = query.data.split('_')
            chat_id = query.message.chat_id
            role_name = user_roles[chat_id][role_id]['name']
            del user_roles[chat_id][role_id]
            await query.message.reply_text(f"Роль {role_name} была удалена.")
            await query.message.edit_reply_markup(reply_markup=None)

    except ValueError as e:
        await query.message.reply_text(f"Ошибка обработки данных кнопки: {str(e)}")
        print(f"Ошибка обработки данных кнопки: {str(e)}")

async def view_roles(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if chat_id not in user_roles or not user_roles[chat_id]:
        await update.message.reply_text("Нет настроенных ролей. Используйте /addrole для добавления.")
        return

    roles_info = "Текущие настройки ролей:\n"
    for role_name, details in user_roles[chat_id].items():
        roles_info += (f"Роль: {details['name']}\nОписание: {details['description']}\n"
                       f"LLM: {details['llm']}\nМакс. длина: {details['max_tokens']}\n"
                       f"Температура: {details['temperature']}\n\n")
    
    await update.message.reply_text(roles_info)

async def clear_roles(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_roles[chat_id] = {}
    await update.message.reply_text("Все роли были очищены.")

async def get_llm_response(prompt, llm, description, max_tokens, temperature):
    try:
        # Отладочное сообщение для проверки контекста
        print(f"Отправка в LLM: {prompt}")

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

async def start_dialog(update: Update, context: ContextTypes.DEFAULT_TYPE, from_button=False):
    chat_id = update.effective_chat.id if not from_button else update.callback_query.message.chat_id
    if chat_id in chat_tasks and not from_button:
        if from_button:
            await update.callback_query.message.reply_text("Диалог уже запущен. Используйте /stop для остановки.")
        else:
            await update.message.reply_text("Диалог уже запущен. Используйте /stop для остановки.")
        return

    if not user_roles.get(chat_id):
        if from_button:
            await update.callback_query.message.reply_text("Нет настроенных ролей. Используйте /addrole для добавления.")
        else:
            await update.message.reply_text("Нет настроенных ролей. Используйте /addrole для добавления.")
        return

    print(f"Запуск диалога для chat_id: {chat_id} с ролями: {user_roles[chat_id]}")  # Отладочное сообщение

    async def dialog_loop():
        cycle_count = 0
        while True:
            for role_id, details in user_roles[chat_id].items():
                # Используем сохраненную историю взаимодействий
                context_messages = "\n".join(
                    [f"{entry['role']}: {entry['message']}" for entry in interaction_history[chat_id][-5:]]
                )
                prompt = f"{details['description']}\nКонтекст:\n{context_messages}"
                
                # Отладочное сообщение для проверки контекста
                print(f"Контекст для {details['name']}: {context_messages}")

                response = await get_llm_response(prompt, details['llm'], details['description'], details['max_tokens'], details['temperature'])
                interaction_history[chat_id].append({'role': details['name'], 'message': response})
                
                # Используем правильный объект для отправки сообщений
                if from_button:
                    await update.callback_query.message.reply_text(f"{details['name']}:\n{response}")
                else:
                    await update.message.reply_text(f"{details['name']}:\n{response}")
                
                await asyncio.sleep(3)  # Задержка в 3 секунды между сообщениями

            cycle_count += 1
            if cycle_count >= 3:
                keyboard = [
                    [InlineKeyboardButton("Продолжить обсуждение", callback_data="continue_dialog")],
                    [InlineKeyboardButton("Закончить обсуждение", callback_data="end_dialog")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                if from_button:
                    await update.callback_query.message.reply_text("3 цикла обсуждения завершены. Хотите продолжить?", reply_markup=reply_markup)
                else:
                    await update.message.reply_text("3 цикла обсуждения завершены. Хотите продолжить?", reply_markup=reply_markup)
                
                break

    task = asyncio.create_task(dialog_loop())
    chat_tasks[chat_id] = task
    if not from_button:
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
    application.add_handler(CommandHandler("deleterole", delete_role))
    application.add_handler(CallbackQueryHandler(button))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))

    print("🚀 Бот для настройки ролей запущен...")
    application.run_polling()

if __name__ == '__main__':
    main() 
