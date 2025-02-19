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
            parts = query.data.split('_')
            if len(parts) != 3:
                await query.message.reply_text("Ошибка: неверный формат данных кнопки.")
                return

            _, role_name, llm = parts

            chat_id = query.message.chat_id

            if role_name not in user_roles[chat_id]:
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
