# words.sh: what the Mac side says, in English and Russian (SWITCH-1, 2026-11-16). Sourced by the
# "Join my brain" app and by spoke.sh in its window mode; bash 3.2 (the Mac's own), no arrays of arrays.
# w <key> [arg]  prints the words for SPOKE_LANG (en or ru; anything else is en).

w() {
    local k=$1 a=${2:-}
    if [ "${SPOKE_LANG:-en}" = ru ]; then
        case "$k" in
            title) echo "Подключить мозг" ;;
            bad_sig) echo "Эти файлы не те, что подписал ваш мозг. Ничего не изменено. Скачайте файл заново на странице мозга." ;;
            intro) printf '%s\n\n%s\n\n%s' \
                "Мозг подключится к этому компьютеру через свою собственную закрытую сеть." \
                "Сначала он только СМОТРИТ: сколько фото, документов и музыки, какого размера и возраста. Без названий. Пароли, письма, сообщения и браузер он не открывает никогда. Он ничего не переносит без вашего «да» и ничего не удаляет." \
                "Ключ вашего мозга: $a (тот же, что на странице мозга)." ;;
            b_join) echo "Подключить" ;; b_show) echo "Показать шаги" ;; b_not) echo "Не сейчас" ;;
            b_done) echo "Готово" ;; b_ok) echo "Хорошо" ;; b_skip) echo "Пропустить" ;; b_install) echo "Установить" ;;
            nothing) echo "Ничего не изменено." ;;
            password) echo "Сейчас Mac спросит ваш пароль: он нужен один раз, чтобы установить Tailscale (закрытую сеть между мозгом и компьютером)." ;;
            vpn) echo "Если Mac спросит про «конфигурацию VPN» или «системное расширение» для Tailscale, нажмите «Разрешить». Если откроются Системные настройки, включите Tailscale там и вернитесь сюда." ;;
            remote) printf '%s\n\n%s\n%s\n\n%s' \
                "Открылись Системные настройки, раздел «Общий доступ»." \
                "1. Включите «Удалённый вход»." \
                "2. Нажмите (i) рядом с ним и включите «Разрешить полный доступ к диску для удалённых пользователей»; в «Разрешить доступ» оставьте только себя." \
                "Это дверь, в которую стучится только ваш мозг. Нажмите «Готово», когда оба переключателя включены." ;;
            remote_not) echo "«Удалённый вход» ещё выключен. Включите его в открытом окне и нажмите «Готово»." ;;
            fda_on) printf '%s\n\n%s' \
                "«Удалённый вход» уже включён." \
                "Проверьте одно: нажмите (i) рядом с ним в «Общем доступе» и включите «Разрешить полный доступ к диску для удалённых пользователей». Без этого мозг не увидит Документы, Рабочий стол и Загрузки." ;;
            tools) echo "Чтобы потом перенести файлы в мозг, Mac нужны бесплатные инструменты Apple (Command Line Tools, около 15 минут загрузки). Установить сейчас? Mac покажет своё окно: нажмите «Установить»." ;;
            done) printf '%s\n\n%s' "Готово. Мозг видит этот компьютер." "Вернитесь на страницу мозга: $a" ;;
            failed) printf '%s\n\n%s' "Остановлено: $a" "После этого шага ничего не изменено." ;;
            not_mac) echo "эта программа для Mac" ;;
            old_mac) echo "нужна macOS 13 или новее (здесь $a)" ;;
            leave_ask) echo "Отключить мозг от этого компьютера? Ключ мозга удаляется, компьютер выходит из его сети." ;;
            left) echo "Готово: мозг больше не может достучаться до этого компьютера." ;;
            leave_remote) echo "До подключения «Удалённый вход» был выключен. Открылся «Общий доступ»: выключите его там." ;;
            *) echo "$k" ;;
        esac
        return
    fi
    case "$k" in
        title) echo "Join my brain" ;;
        bad_sig) echo "These files are not the ones your brain signed. Nothing was changed. Download the file again from your brain's page." ;;
        intro) printf '%s\n\n%s\n\n%s' \
            "Your brain joins this computer through its own private network." \
            "First it only LOOKS: how many photos, documents and songs, how big, how old. No names. It never opens your passwords, mail, messages or browser. It moves nothing without your yes, and it never deletes." \
            "Your brain's key: $a (the same as on your brain's page)." ;;
        b_join) echo "Join" ;; b_show) echo "Show the steps" ;; b_not) echo "Not now" ;;
        b_done) echo "Done" ;; b_ok) echo "OK" ;; b_skip) echo "Skip" ;; b_install) echo "Install" ;;
        nothing) echo "Nothing was changed." ;;
        password) echo "Your Mac asks for your password now: once, to install Tailscale (the private network between your brain and this computer)." ;;
        vpn) echo "If your Mac asks about a \"VPN configuration\" or a \"system extension\" for Tailscale, press Allow. If System Settings opens, turn Tailscale on there and come back here." ;;
        remote) printf '%s\n\n%s\n%s\n\n%s' \
            "System Settings opened at Sharing." \
            "1. Turn on Remote Login." \
            "2. Press the (i) beside it and turn on \"Allow full disk access for remote users\"; under \"Allow access for\" keep only yourself." \
            "This is the door only your brain knocks on. Press Done when both switches are on." ;;
        remote_not) echo "Remote Login is still off. Turn it on in the window that opened, then press Done." ;;
        fda_on) printf '%s\n\n%s' \
            "Remote Login is already on." \
            "Check one thing: press the (i) beside it in Sharing and turn on \"Allow full disk access for remote users\". Without it your brain cannot see Documents, Desktop and Downloads." ;;
        tools) echo "To bring files into your brain later, your Mac needs Apple's free developer tools (Command Line Tools, about 15 minutes to download). Install them now? Your Mac shows its own window: press Install." ;;
        done) printf '%s\n\n%s' "Done. Your brain can see this computer." "Go back to your brain's page: $a" ;;
        failed) printf '%s\n\n%s' "Stopped: $a" "Nothing after this step was changed." ;;
        not_mac) echo "this program is for a Mac" ;;
        old_mac) echo "macOS 13 or newer is needed (this is $a)" ;;
        leave_ask) echo "Take your brain off this computer? Its key is removed and the computer leaves its network." ;;
        left) echo "Done: your brain can no longer reach this computer." ;;
        leave_remote) echo "Remote Login was off before you joined. Sharing opened: turn it off there." ;;
        *) echo "$k" ;;
    esac
}

# dialog <text> <button>... : one macOS dialog, the last button the default; prints the pressed button
# ("" when closed). Arguments go to AppleScript as argv, never pasted into its source.
dialog() {
    local text=$1; shift
    osascript - "$(w title)" "$text" "$@" <<'AS' 2>/dev/null
on run argv
    set t to item 1 of argv
    set m to item 2 of argv
    set bs to items 3 thru -1 of argv
    activate
    try
        return button returned of (display dialog m buttons bs default button (count of bs) with title t)
    on error
        return ""
    end try
end run
AS
}
