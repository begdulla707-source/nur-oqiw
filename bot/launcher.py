from . import main
from .subscriptions import install_subscription_admin

# main.py registers its normal handlers first. Install the subscription manager
# afterwards and put its filtered admin handler before the catch-all message handler.
check_subscription, subscription_keyboard = install_subscription_admin(
    main.dp, main.bot, main, main.ADMIN
)

# Replace the original single-channel subscription check and keyboard globally.
# Existing handlers resolve these globals at call time.
main.subscribed = check_subscription
main.sub_kb = subscription_keyboard

if __name__ == "__main__":
    import asyncio
    asyncio.run(main.run())
