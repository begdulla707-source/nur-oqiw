"""Keep a transient Telegram API stall from blocking the Render web process."""
import asyncio
import logging
try:
    from aiogram import Bot
    _original_set_webhook = Bot.set_webhook
    async def _safe_set_webhook(self, *args, **kwargs):
        try:
            return await asyncio.wait_for(_original_set_webhook(self, *args, **kwargs), timeout=12)
        except asyncio.TimeoutError:
            logging.getLogger("nur-oqiw").error("Telegram set_webhook timed out; continuing server startup")
            return False
        except Exception:
            logging.getLogger("nur-oqiw").exception("Telegram set_webhook failed")
            return False
    Bot.set_webhook = _safe_set_webhook
except Exception:
    pass
