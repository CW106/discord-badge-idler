# Discord Badge Idler

**English** | [繁體中文](README.zh-TW.md)

A small Windows app that grows Discord's activity badges by running dummy "games" that Discord detects as real ones.

| Badge | What the app does |
| --- | --- |
| Game hours (Casual → … → Unshakeable → Eternal, 5,000 h) | Keeps a dummy game running so your play time keeps going up |
| Games played (Sampler → … → Maverick → Polymath → Universalist, 100+) | Cycles through games you haven't played, a few minutes each |
| Streaming (Newcomer → … → Star → Phenomenon) | Opens a window you can Go Live with. Someone still has to watch. |

The interface uses a dark, Discord-style theme and follows your Windows display language (Traditional Chinese or English). You can switch it any time from the language menu at the top right.

## How it works

1. Downloads Discord's public list of detectable games, which includes each game's executable name.
2. Uses a tiny window program as the dummy game. The EXE has it built in; the Python version builds it with the C# compiler that ships with Windows (`csc.exe`).
3. Copies that program under a game's executable name and runs it. The Discord app sees it and shows "Playing" with that game's name.

It doesn't need your Discord token and doesn't modify the Discord app. Nothing is sent to Discord except what the official app already reports when it detects a game.

## Download

- **EXE (recommended):** download `DiscordBadgeIdler.exe` from the [latest release](../../releases/latest) and run it. It doesn't need Python or any other tools. A GitHub Actions workflow compiles it to native code with Nuitka on every update.
- **Python version:** put `discord_badge_idler.py` and `start.bat` in the same folder and double-click `start.bat`. If it can't find Python 3.8+ with tkinter, it offers to install it for you.

Either way you need Windows 10 or 11 and the Discord desktop app, open and signed in.

Older versions (v1.2 and later) are on the [Releases](../../releases) page, and [CHANGELOG.md](CHANGELOG.md) lists what changed in each one.

## Usage

1. Open `DiscordBadgeIdler.exe` (or `start.bat`).
2. If something's missing or not working, click **Check & repair** on the Help tab (see below).
3. **Game hours** tab: click *Start hours mode*. After about 30 seconds, check that Discord shows "Playing …" (or look at Discord Settings → Registered Games). If it doesn't, click *Not detected by Discord? Switch game*.
4. **Games played** tab: enter how many games Discord shows now and your target, then click *Start games-played mode*.
5. **Streaming** tab: click *Open stream window*, then share that window in a voice channel. The hours only count while someone watches.

### Options

- **Run at once (experimental):** runs up to 100 dummy games at the same time. If Discord counts each game separately, hours add up faster. This isn't confirmed, so compare your badge after a day.
- **Show** menu in the game list: *All games*, *Opened before*, *Never opened*, or *New games*. Random picks, including the extra games for *Run at once*, follow it. Games-played mode always uses games the app has never opened.
- **New games:** the game list updates itself every day, even while the app stays open. When Discord adds games, the app tells you which ones and marks them with ★ for 14 days.
- **Open this app when Windows starts** and **Start hours mode when the app opens:** idling resumes by itself after a restart.
- **Stop automatically after N hours of idling** (Game hours tab): hours mode stops by itself once it has idled that long, and Windows can go to sleep again. Time while Discord is closed doesn't count. If you turn it on or change it while hours mode is running, the countdown starts from that moment.
- While idling, the app keeps Windows from going to sleep on its own. The screen can still turn off.
- **Open Discord** (next to the Discord status) starts the Discord app for you. When you start idling while Discord is closed, the app offers to open it.

### Check & repair

The **Check & repair** button on the Help tab checks everything the app depends on and fixes what it can:

- the data folder can be written to;
- the dummy game runner exists (it's rebuilt if missing) and a test launch works, which catches antivirus or Smart App Control blocks;
- the game list is loaded (it's downloaded again if not);
- Discord is installed and running (it offers to open Discord, or the download page if it isn't installed).

If the app ever crashes, it shows the error in a pop-up and saves the details to `crash_log.txt` in the data folder. The Python version's `start.bat` also saves startup errors to `last_error.txt`.

The app keeps its files (dummy executables, the cached game list, settings and a log) in `%LOCALAPPDATA%\DiscordBadgeIdler`.

## Limitations

- Time can't be sped up. One hour idled is one hour; going from 2,000 to 5,000 hours takes about 125 days running 24/7.
- Streaming hours need a real viewer. This app doesn't automate Discord accounts, because self-bots are against Discord's rules.
- Badge progress may take up to a day to update.
- Discord can change how detection works at any time, so there's no guarantee the time counts.

## Disclaimer

Faking game activity may violate Discord's Terms of Service and could lead to badge resets or action against your account. Use it at your own risk. This project isn't affiliated with or endorsed by Discord.
