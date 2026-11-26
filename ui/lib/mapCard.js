// Your map (ORGANISE-1, 2026-11-26): the words (en, ru, de by the console's lang key) and the pure rules of
// the home's map card. After the move-in the brain proposes the person's own areas (api/organise.py); the
// card shows them as chips with counts, press to see the items, rename, merge or move by pressing, and one
// "Looks right". ui/components/MapCard.js draws it; tests/test_organise.py runs this file under node.
const { ruPlural } = require('./moveIn')

const EN = {
  title: 'Your map',
  found: (docs, chats, areas) => `This is what I found of yours: ${n(docs)} ${docs === 1 ? 'document' : 'documents'}` +
    (chats ? ` and ${n(chats)} ${chats === 1 ? 'chat' : 'chats'}` : '') + `, in ${areas} areas.`,
  making: 'Making your map from what arrived…',
  nothing: 'Nothing is moved or relabelled before you say it looks right.',
  looks: 'Looks right',
  saving: 'Saving…',
  set: (areas) => `Your map is set: ${areas} areas. Every document carries its area, the Knowledge page and the answers can keep to one.`,
  world: (p) => `Written as ${p}: one folder per area, each with an index. Your files stay where they are.`,
  undo: 'Undo',
  undone: 'Undone: the labels are back as they were. The map waits here again.',
  open: 'Open the map',
  close: 'Close',
  rename: 'Rename',
  save: 'Save',
  merge: 'Merge into…',
  mergeInto: (a) => `Merge into ${a}`,
  move: 'Move to…',
  items: (c, d, ch) => `${n(c)}: ${n(d)} ${d === 1 ? 'document' : 'documents'}, ${n(ch)} ${ch === 1 ? 'chat' : 'chats'}`,
  more: (k) => `Show ${n(k)} more`,
  chat: 'chat',
  failed: 'That did not work. Try again in a moment.',
  arrived: (k) => `${n(k)} new since then were sorted in.`,
}
const RU = {
  title: 'Ваша карта',
  found: (docs, chats, areas) => `Вот что я нашёл вашего: ${n(docs)} ${ruPlural(docs, ['документ', 'документа', 'документов'])}` +
    (chats ? ` и ${n(chats)} ${ruPlural(chats, ['чат', 'чата', 'чатов'])}` : '') + `, ${areas} ${ruPlural(areas, ['область', 'области', 'областей'])}.`,
  making: 'Составляю карту из того, что пришло…',
  nothing: 'Ничего не переносится и не переименовывается, пока вы не скажете, что всё верно.',
  looks: 'Всё верно',
  saving: 'Сохраняю…',
  set: (areas) => `Карта готова: ${areas} ${ruPlural(areas, ['область', 'области', 'областей'])}. У каждого документа своя область, в Знаниях и в ответах можно держаться одной.`,
  world: (p) => `Записано в ${p}: папка на каждую область, в каждой оглавление. Файлы остаются на своих местах.`,
  undo: 'Отменить',
  undone: 'Отменено: метки как были. Карта снова ждёт здесь.',
  open: 'Открыть карту',
  close: 'Закрыть',
  rename: 'Переименовать',
  save: 'Сохранить',
  merge: 'Объединить с…',
  mergeInto: (a) => `Объединить с «${a}»`,
  move: 'Перенести в…',
  items: (c, d, ch) => `${n(c)}: ${n(d)} ${ruPlural(d, ['документ', 'документа', 'документов'])}, ${n(ch)} ${ruPlural(ch, ['чат', 'чата', 'чатов'])}`,
  more: (k) => `Показать ещё ${n(k)}`,
  chat: 'чат',
  failed: 'Не получилось. Попробуйте ещё раз через минуту.',
  arrived: (k) => `${n(k)} новых с тех пор разобраны.`,
}
const DE = {
  title: 'Deine Karte',
  found: (docs, chats, areas) => `Das habe ich von dir gefunden: ${n(docs)} ${docs === 1 ? 'Dokument' : 'Dokumente'}` +
    (chats ? ` und ${n(chats)} ${chats === 1 ? 'Chat' : 'Chats'}` : '') + `, in ${areas} Bereichen.`,
  making: 'Ich mache deine Karte aus dem, was angekommen ist…',
  nothing: 'Nichts wird verschoben oder umbenannt, bevor du sagst, dass es stimmt.',
  looks: 'Stimmt so',
  saving: 'Speichere…',
  set: (areas) => `Deine Karte steht: ${areas} Bereiche. Jedes Dokument trägt seinen Bereich, die Wissensseite und die Antworten können bei einem bleiben.`,
  world: (p) => `Geschrieben als ${p}: ein Ordner pro Bereich, jeder mit einem Index. Deine Dateien bleiben, wo sie sind.`,
  undo: 'Rückgängig',
  undone: 'Rückgängig gemacht: die Bereiche sind wie vorher. Die Karte wartet hier wieder.',
  open: 'Karte öffnen',
  close: 'Schließen',
  rename: 'Umbenennen',
  save: 'Speichern',
  merge: 'Zusammenlegen mit…',
  mergeInto: (a) => `Mit ${a} zusammenlegen`,
  move: 'Verschieben nach…',
  items: (c, d, ch) => `${n(c)}: ${n(d)} ${d === 1 ? 'Dokument' : 'Dokumente'}, ${n(ch)} ${ch === 1 ? 'Chat' : 'Chats'}`,
  more: (k) => `${n(k)} weitere zeigen`,
  chat: 'Chat',
  failed: 'Das hat nicht geklappt. Gleich noch einmal versuchen.',
  arrived: (k) => `${n(k)} neue seitdem einsortiert.`,
}
const MAP_TEXT = { en: EN, ru: RU, de: DE }

function n(x) { return Number(x || 0).toLocaleString('en-US') }

function mapWords(lang) { return MAP_TEXT[lang] || EN }

// What the card shows for GET /organise:
// hidden (no map and nothing to map yet, or the api is older), propose (ready, no map: build it now),
// proposed (the open map, the yes waits), accepted (the map in force, folded to one line with Undo).
function mapStep(st) {
  if (!st || typeof st !== 'object') return 'hidden'
  if (st.state === 'proposed' && Array.isArray(st.areas) && st.areas.length) return 'proposed'
  if (st.state === 'accepted' && Array.isArray(st.areas) && st.areas.length) return 'accepted'
  if ((st.state === 'none' || !st.state) && st.ready) return 'propose'
  return 'hidden'
}

// The chips: one per area, largest first, the archive last; the count is the area's own.
function chips(st) {
  const areas = (st && Array.isArray(st.areas)) ? st.areas.slice() : []
  areas.sort((a, b) => (!!a.archive - !!b.archive) || ((b.count || 0) - (a.count || 0)))
  return areas.map(a => ({ id: a.id, name: a.name, count: a.count || 0, archive: !!a.archive }))
}

// The edits the card sends (POST /organise/edit), checked before they leave.
function renameOp(area, name) {
  const v = String(name || '').replace(/\s+/g, ' ').trim().slice(0, 40)
  return v ? { op: 'rename', area, name: v } : null
}
function mergeOp(area, into) { return area && into && area !== into ? { op: 'merge', area, into } : null }
function moveOp(item, to) { return item && to ? { op: 'move', item, to } : null }

// The labels' counts after the yes, without the empty key: how many arrived since and went where.
function arrivedSince(st) {
  const lab = st && st.labels
  if (!lab || typeof lab !== 'object') return 0
  const inMap = (st.areas || []).reduce((s, a) => s + (a.count || 0), 0)
  const labelled = Object.entries(lab).filter(([k]) => k).reduce((s, [, v]) => s + (v || 0), 0)
  return Math.max(0, labelled - inMap)
}

module.exports = { MAP_TEXT, mapWords, mapStep, chips, renameOp, mergeOp, moveOp, arrivedSince }
