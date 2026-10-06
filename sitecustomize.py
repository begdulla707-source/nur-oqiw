"""Runtime safety patches for the Telegram webhook process."""
import asyncio
import logging

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

    # Telegram must receive HTTP 200 immediately. Slow handlers were causing
    # Telegram to retry the same update for minutes, making /start appear dead.
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

    # Expired callback queries must never turn the webhook into HTTP 500.
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
except Exception:
    log.exception("Runtime safety patch initialization failed")
