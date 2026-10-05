"""Keep Telegram webhook setup from blocking the Render web process."""
import asyncio
import logging
try:
    from aiogram import Bot
    _original_set_webhook = Bot.set_webhook
    async def _safe_set_webhook(self, *args, **kwargs):
        async def setup():
            try:
                await asyncio.wait_for(_original_set_webhook(self, *args, **kwargs), timeout=12)
                logging.getLogger("nur-oqiw").info("Telegram webhook setup completed")
            except asyncio.TimeoutError:
                logging.getLogger("nur-oqiw").error("Telegram webhook setup timed out")
            except Exception:
                logging.getLogger("nur-oqiw").exception("Telegram webhook setup failed")
        asyncio.create_task(setup())
        return True
    Bot.set_webhook = _safe_set_webhook
except Exception:
    pass
