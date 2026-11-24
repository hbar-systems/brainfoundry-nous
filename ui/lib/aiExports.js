// Where each AI's export button is, for the move-in import card (MOVE-IN-2, 2026-11-16).
// One entry per AI the brain imports through POST /documents/import-chats; the file is
// detected on upload, no picker. 'agents' (MEMBERS-11, 2026-11-23): Codex and Claude Code keep their
// history on the computer; the survey brings it, a single session .jsonl can be dropped here.
// verified mirrors scripts/import_chats.py FORMATS: false means
// the file shape follows third-party descriptions (docs/IMPORT.md "Other AIs (2026-11-16)").
// Plain ES module, no imports; the home card renders it.

export const AI_EXPORTS = [
  {
    key: 'chatgpt', name: 'ChatGPT', verified: true, url: 'https://chatgpt.com',
    steps: {
      en: 'chatgpt.com: Settings > Data controls > Export data. The zip comes by email; drop it here as it came.',
      ru: 'chatgpt.com: Настройки > Управление данными (Data controls) > Экспорт данных. Архив придёт на почту, положите его сюда как есть.',
    },
  },
  {
    key: 'claude', name: 'Claude', verified: true, url: 'https://claude.ai/settings/data-privacy-controls',
    steps: {
      en: 'claude.ai: Settings > Privacy > Export data. The link in the email opens one zip or a list of downloads. Drop the conversations zip here (conversations-000.zip, every part if there are several); frames and the other zips hold no chats.',
      ru: 'claude.ai: Настройки > Конфиденциальность (Privacy) > Экспорт данных. Ссылка в письме открывает один архив или список загрузок. Положите сюда архив conversations (conversations-000.zip, все части, если их несколько); в frames и других архивах разговоров нет.',
    },
  },
  {
    key: 'gemini', name: 'Gemini', verified: false, url: 'https://takeout.google.com',
    steps: {
      en: 'takeout.google.com: Deselect all, tick My Activity, press All activity data included, Deselect all, tick Gemini Apps, OK, Next step, Create export. Drop the zip here.',
      ru: 'takeout.google.com: Отменить выбор, отметьте «Мои действия», нажмите «Включены все данные о действиях», снимите все отметки, оставьте Gemini Apps, OK, Далее, Создать экспорт. Положите сюда полученный архив.',
    },
  },
  {
    key: 'deepseek', name: 'DeepSeek', verified: false, url: 'https://chat.deepseek.com',
    steps: {
      en: 'chat.deepseek.com: your profile (bottom left) > Settings > Data > Export data. Drop the zip or its conversations.json here.',
      ru: 'chat.deepseek.com: профиль (внизу слева) > Настройки > Данные > Экспорт данных. Положите сюда архив или файл conversations.json из него.',
    },
  },
  {
    key: 'grok', name: 'Grok', verified: false, url: 'https://accounts.x.ai/data',
    steps: {
      en: 'accounts.x.ai/data (or grok.com: Settings > Data controls): Download account data. Drop the zip or its prod-grok-backend.json here.',
      ru: 'accounts.x.ai/data (или grok.com: Настройки > Управление данными): «Скачать данные аккаунта». Положите сюда архив или файл prod-grok-backend.json из него.',
    },
  },
  {
    key: 'copilot', name: 'Copilot', verified: false, url: 'https://account.microsoft.com/privacy',
    steps: {
      en: 'account.microsoft.com/privacy: Privacy > Empower your productivity > Copilot > Copilot apps > Export all activity history. Drop the CSV here.',
      ru: 'account.microsoft.com/privacy: Конфиденциальность > Copilot > Приложения Copilot > «Экспортировать весь журнал действий». Положите сюда полученный CSV-файл.',
    },
  },
  {
    key: 'perplexity', name: 'Perplexity', verified: false, url: 'https://www.perplexity.ai/account/details',
    steps: {
      en: 'No bulk file the brain can read yet. Open a thread, press the ... menu > Export > Markdown or PDF, and drop that file here, or copy the thread and paste it.',
      ru: 'Общего файла, который мозг умеет читать, пока нет. Откройте беседу, меню ... > Export > Markdown или PDF, и положите файл сюда, или скопируйте беседу и вставьте текстом.',
    },
  },
  {
    key: 'lechat', name: 'Le Chat', verified: false, url: 'https://admin.mistral.ai/account/export',
    steps: {
      en: 'admin.mistral.ai/account/export: press Export. Drop the file here; if it is not read, paste the conversation instead.',
      ru: 'admin.mistral.ai/account/export: нажмите Export. Положите файл сюда; если он не прочитается, вставьте беседу текстом.',
    },
  },
  {
    key: 'agents', name: 'Codex, Claude Code', verified: true, url: '',
    steps: {
      en: 'Their history is on your computer, not in an export: Bring in this computer brings it. One session: drop its .jsonl from ~/.codex/sessions or ~/.claude/projects here.',
      ru: 'Их история лежит на компьютере, а не в экспорте: её переносит «Перенести этот компьютер». Одну сессию: положите сюда её .jsonl из ~/.codex/sessions или ~/.claude/projects.',
    },
  },
  {
    key: 'pasted', name: 'Any other AI', verified: true, url: '',
    steps: {
      en: 'Copy the conversation and paste it here, or drop a saved page, text, Markdown or PDF. It becomes one conversation.',
      ru: 'Скопируйте беседу и вставьте её сюда или положите сохранённую страницу, текст, Markdown или PDF. Получится одна беседа.',
    },
  },
]

// The short list of names for the card's first line.
export function aiExportsLine(lang) {
  const names = AI_EXPORTS.filter((a) => a.key !== 'pasted').map((a) => a.name).join(', ')
  return lang === 'ru'
    ? `${names} и любой другой ИИ: просто вставьте текст.`
    : `${names}, and any other AI as pasted text.`
}
