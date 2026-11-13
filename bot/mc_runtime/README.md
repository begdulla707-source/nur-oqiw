# Optional Minecraft runtime

The admin-only Minecraft bridge runs in a separately supervised Node.js child
process inside the existing service. It exposes no HTTP endpoint and does not
receive the Telegram bot token or database credentials.

On MCWeb Linux x86-64, prepare or restore the ignored runtime cache with:

```sh
python bot/mc_runtime/setup.py
```

The installer checks a pinned Node.js archive hash and uses the committed npm
lockfile. Run it when the Minecraft child process is stopped. The Python test
service still starts if the optional runtime is missing; Minecraft accounts
cannot connect until it is installed. No Minecraft or Telegram credential is
stored in this directory.

`/boxpvp` re-entry and captcha recognition depend on the server's actual
messages and map protocol. These must be tested with a real authorized account.
