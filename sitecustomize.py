"""Runtime safety patches for the Telegram webhook process."""
import asyncio
import logging
import threading
import sys

log=logging.getLogger("nur-oqiw")

try:
    from aiogram import Bot, Dispatcher
    from aiogram.types import CallbackQuery

    _original_set_webhook = Bot.set_webhook
    async def _safe_set_webhook(self, *args, **kwargs):
        async def setup():
            try:
                await asyncio.wait_for(_original_set_webhook(self, *args, **kwargs), timeout=12)
                log.info("Telegram webhook setup completed")
            except asyncio.TimeoutError:
                log.error("Telegram webhook setup timed out")
            except Exception:
                log.exception("Telegram webhook setup failed")
        asyncio.create_task(setup())
        return True
    Bot.set_webhook = _safe_set_webhook

    _original_feed_update = Dispatcher.feed_update
    async def _fast_feed_update(self, bot, update, *args, **kwargs):
        async def run():
            try:
                await _original_feed_update(self, bot, update, *args, **kwargs)
            except Exception:
                log.exception("Telegram update handler failed")
        asyncio.create_task(run())
        return update
    Dispatcher.feed_update = _fast_feed_update

    _original_answer = CallbackQuery.answer
    async def _safe_answer(self, *args, **kwargs):
        try:
            return await _original_answer(self, *args, **kwargs)
        except Exception as exc:
            text=str(exc).lower()
            if "too old" in text or "query id is invalid" in text or "query is too old" in text:
                return None
            raise
    CallbackQuery.answer = _safe_answer

    def _restore_user_menu():
        try:
            main=sys.modules.get("__main__")
            if main and getattr(main,"__name__","")=="__main__" and hasattr(main,"user_menu"):
                main.web_kb = main.user_menu
                log.info("User profile/tariff menu restored")
        except Exception:
            pass
    threading.Timer(2.0, _restore_user_menu).start()
except Exception:
    log.exception("Runtime safety patch initialization failed")
