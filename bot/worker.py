"""Run Telegram updates in a dedicated MCWeb background worker."""

import asyncio
import logging
import os

logger = logging.getLogger("nur-oqiw.worker")


async def run_polling_worker():
    if os.getenv("NUR_WORKER_ENABLED") != "1":
        logger.info("Worker is safely idle until NUR_WORKER_ENABLED=1")
        await asyncio.Event().wait()

    from .main import bot, dp, logger as app_logger

    try:
        info = await bot.get_webhook_info()
        if info.url:
            app_logger.info("Replacing Telegram webhook with background polling")
        await bot.delete_webhook(drop_pending_updates=False)
        app_logger.info("Telegram polling worker started; pending updates are preserved")
        await dp.start_polling(
            bot,
            allowed_updates=dp.resolve_used_update_types(),
            polling_timeout=25,
            close_bot_session=False,
        )
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(run_polling_worker())
