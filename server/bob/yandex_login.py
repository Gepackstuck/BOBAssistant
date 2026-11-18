import json
import time

from yandex_music import Client

from .config import ROOT

TOKEN_PATH = ROOT / "secrets" / "yandex_music_token.json"


def save(token) -> None:
    TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    TOKEN_PATH.write_text(json.dumps({
        "access_token": token.access_token,
        "refresh_token": getattr(token, "refresh_token", None),
        "expires_at": time.time() + (getattr(token, "expires_in", 0) or 0),
    }))
    TOKEN_PATH.chmod(0o600)


def show_code(code) -> None:
    print()
    print(f"1. Откройте в браузере: {code.verification_url}")
    print(f"2. Введите код: {code.user_code}")
    print("3. Войдите в нужный аккаунт Яндекса и подтвердите доступ.")
    print()
    print("Жду подтверждения…", flush=True)


def login() -> None:
    token = Client().device_auth(on_code=show_code, device_name="BOBAssistant")
    save(token)
    client = Client(token.access_token).init()
    account = client.me.account
    print(f"Готово. Вошли как {account.display_name or account.login}. Подписка Плюс: {'есть' if client.me.plus and client.me.plus.has_plus else 'не найдена'}.")
    print(f"Токен сохранён в {TOKEN_PATH.relative_to(ROOT.parent)} (в git не попадает).")
