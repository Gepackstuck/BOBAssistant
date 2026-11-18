# Токен Яндекс Музыки

Для музыки нужен токен аккаунта с подпиской Плюс. Официального API у Яндекс Музыки нет, поэтому
используется неофициальная библиотека [yandex-music](https://github.com/MarshalX/yandex-music-api).
Токен даёт полный доступ к аккаунту: не показывайте его никому, не вставляйте в чат и в git.

## Способ 1. Вход по коду (проще и безопаснее)

```sh
cd server
uv run bob yandex-login
```

Команда покажет адрес и код. Откройте адрес в браузере, введите код, войдите в нужный аккаунт Яндекса и
подтвердите доступ. Токен сохранится в `server/secrets/yandex_music_token.json` (права `600`, в git не попадает).

## Способ 2. Вручную через браузер

1. Откройте `https://oauth.yandex.ru/authorize?response_type=token&client_id=23cabbbdc6cd418abb4b39c32c41195d`.
2. Войдите и разрешите доступ.
3. Браузер перенаправит на адрес вида `https://music.yandex.ru/#access_token=...&token_type=bearer&expires_in=...`.
   Скопируйте адрес до второго перенаправления (удобно включить замедление сети в DevTools).
4. Токен — значение `access_token` после `#`.

Сохраните его, не показывая на экране:

```sh
cd server
read -rs "T?Вставьте токен и нажмите Enter: " && printf '{"access_token": "%s"}' "$T" > secrets/yandex_music_token.json && chmod 600 secrets/yandex_music_token.json && unset T
```

## Проверка

```sh
uv run bob music "Земфира"
```

Покажет найденные треки и проверит ссылку на первый, ничего не воспроизводя.

Источник: [документация библиотеки](https://ym.marshal.dev/en/main/token.html).
