# Discord Badge Idler

**English** | [繁體中文](README.zh-TW.md)

A small Windows app that grows Discord's activity badges by running dummy "games" that Discord detects as real ones.

| Badge | What the app does |
| --- | --- |
| Game hours (Casual → … → Unshakeable → Eternal, 5,000 h) | Keeps a dummy game running so your play time keeps going up |
| Games played (Sampler → … → Maverick → Polymath → Universalist, 100+) | Cycles through games you haven't played, a few minutes each |
| Streaming (Newcomer → … → Star → Phenomenon) | Opens a window you can Go Live with. Someone still has to watch. |

The interface follows your Windows display language (Traditional Chinese or English). You can switch it any time from the language menu at the top right.

## How it works

1. Downloads Discord's public list of detectable games, which includes each game's executable name.
2. Builds a tiny window program with the C# compiler that ships with Windows (`csc.exe`).
3. Copies that program under a game's executable name and runs it. The Discord app sees it and shows "Playing" with that game's name.

It doesn't need your Discord token and doesn't modify the Discord app. Nothing is sent to Discord except what the official app already reports when it detects a game.

## Requirements

- Windows 10 or 11 (with .NET Framework 4, which is installed by default)
- Python 3.8 or newer with tkinter (the python.org installer includes it)
- The Discord desktop app, open and signed in

## Usage

1. Put `discord_badge_idler.py` and `start.bat` in the same folder.
2. Double-click `start.bat`, or run `python discord_badge_idler.py`.
3. **Game hours** tab: click *Start hours mode*. After about 30 seconds, check that Discord shows "Playing …" (or look at Discord Settings → Registered Games). If it doesn't, click *Not detected by Discord? Switch game*.
4. **Games played** tab: enter how many games Discord shows now and your target, then click *Start games-played mode*.
5. **Streaming** tab: click *Open stream window*, then share that window in a voice channel. The hours only count while someone watches.

### Options

- **Run at once (experimental):** runs up to 100 dummy games at the same time. If Discord counts each game separately, hours add up faster. This isn't confirmed, so compare your badge after a day.
- **Show** menu in the game list: *All games*, *Opened before*, or *Never opened*. Random picks, including the extra games for *Run at once*, follow it. Games-played mode always uses games the app has never opened.
- **Open this app when Windows starts** and **Start hours mode when the app opens:** idling resumes by itself after a restart.
- While idling, the app keeps Windows from going to sleep on its own. The screen can still turn off.

The app keeps its files (dummy executables, the cached game list, settings and a log) in `%LOCALAPPDATA%\DiscordBadgeIdler`.

## Limitations

- Time can't be sped up. One hour idled is one hour; going from 2,000 to 5,000 hours takes about 125 days running 24/7.
- Streaming hours need a real viewer. This app doesn't automate Discord accounts, because self-bots are against Discord's rules.
- Badge progress may take up to a day to update.
- Discord can change how detection works at any time, so there's no guarantee the time counts.

## Disclaimer

Faking game activity may violate Discord's Terms of Service and could lead to badge resets or action against your account. Use it at your own risk. This project isn't affiliated with or endorsed by Discord.
