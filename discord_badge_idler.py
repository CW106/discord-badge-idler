# -*- coding: utf-8 -*-
"""
Discord Badge Idler / Discord 徽章掛機助手
=========================================

EN: Keeps Discord's activity badges growing by running dummy "games" that Discord detects:
    game hours (UNSHAKEABLE -> Eternal), games played (MAVERICK -> Universalist),
    plus a window you can stream (streaming hours still need a real viewer).
    Windows 10/11 + Python 3.8+ (with tkinter). No extra packages.
    Run: double-click start.bat, or  python discord_badge_idler.py

中文：用「假遊戲」讓 Discord 以為你在玩遊戲，自動累積遊戲時數徽章、遊戲款數徽章，
     另外提供一個可以拿來直播的假遊戲視窗（直播時數一定要有真人在看才會算）。
     需求：Windows 10/11、Python 3.8 以上（要有內建的 tkinter），不用安裝任何套件。
     執行：雙擊 start.bat，或在命令列輸入  python discord_badge_idler.py

原理 / How it works:
  1. 下載 Discord 公開的「可偵測遊戲清單」（每款遊戲對應的 .exe 名稱）。
  2. 用 Windows 內建的 C# 編譯器 (csc.exe) 編譯一個很小的視窗程式。
  3. 把它複製成某款遊戲的 exe 名稱再執行，Discord 看到同名程式就會顯示「正在玩」。

注意 / Note: 這樣做可能違反 Discord 服務條款，請自行承擔風險。
            This may violate Discord's Terms of Service. Use at your own risk.
"""

from __future__ import annotations

import ctypes
import filecmp
import hashlib
import json
import math
import os
import platform
import queue
import random
import re
import shutil
import subprocess
import sys
import threading
import time
import traceback
import urllib.request
import webbrowser
from pathlib import Path

try:
    import tkinter as tk
    import tkinter.font as tkfont
    from tkinter import messagebox, ttk
except ImportError:  # 少數 Python 安裝沒有 tkinter
    tk = None


# ============================================================================
# 基本設定
# ============================================================================

VERSION = "1.5"

# 用 Nuitka 或 PyInstaller 打包成 exe 時為 True
IS_FROZEN = bool(getattr(sys, "frozen", False)) or "__compiled__" in globals()

# Discord 公開的「可偵測遊戲清單」。第二個是開源專案 arRPC 收錄的副本，只在第一個連不上時使用。
DETECTABLE_SOURCES = [
    "https://discord.com/api/v9/applications/detectable",
    "https://raw.githubusercontent.com/OpenAsar/arrpc/main/src/process/detectable.json",
]
LIST_MAX_AGE = 24 * 3600          # 遊戲清單超過一天就重新下載
USER_CLOSED_EXIT_CODE = 2         # 假遊戲視窗被使用者手動關掉時的結束代碼（C# 那邊定義的）
MAX_PARALLEL = 100                # 「同時執行」最多幾款
AUTO_STOP_LIMITS = (0.5, 10000.0)  # 「掛滿幾小時後自動停止」可以設定的範圍（小時）
PICK_MODES = ("all", "opened", "unopened", "new")   # 遊戲清單範圍：全部／開過的／沒開過的／新遊戲
OPENED_MARK = "✓ "                # 清單裡「開過」的遊戲前面加這個記號
NEW_MARK = "★ "                   # 清單裡「新遊戲」前面加這個記號
NEW_GAME_DAYS = 14                # Discord 新增的遊戲，幾天內算「新遊戲」
GAME_RULES_VERSION = 1            # 挑選可模擬遊戲的規則改了就加 1（規則放寬多出來的遊戲不會被當成新遊戲）
LIST_CHECK_MS = 3600 * 1000       # 程式開著時，每小時看一次遊戲清單是不是超過一天沒更新
LIST_RETRY_SECONDS = 3 * 3600     # 清單太舊但更新失敗（例如沒網路）時，隔多久再試一次
DISCORD_PROCESS_NAMES = {"discord.exe", "discordptb.exe", "discordcanary.exe", "discorddevelopment.exe"}
# Discord 電腦版的安裝位置（%LOCALAPPDATA%\<資料夾>\Update.exe）
DISCORD_INSTALLS = (("Discord", "Discord.exe"), ("DiscordPTB", "DiscordPTB.exe"), ("DiscordCanary", "DiscordCanary.exe"))
DISCORD_DOWNLOAD_URL = "https://discord.com/download"
DOTNET_DOWNLOAD_URL = "https://dotnet.microsoft.com/download/dotnet-framework/net48"

# 三種徽章的等級（名稱, 門檻）
HOURS_TIERS = [("Casual", 1), ("Recreational", 5), ("Dedicated", 20), ("Committed", 75), ("Serious", 150),
               ("Devoted", 300), ("Seasoned", 500), ("Ironclad", 1000), ("Unshakeable", 2000), ("Eternal", 5000)]
GAMES_TIERS = [("Sampler", 2), ("Dabbler", 5), ("Enthusiast", 10), ("Ranger", 15), ("Explorer", 20),
               ("Adventurer", 30), ("Voyager", 40), ("Maverick", 60), ("Polymath", 80), ("Universalist", 100)]
STREAM_TIERS = [("Newcomer", 1), ("Fledgling", 5), ("Breakout", 20), ("Standout", 75), ("Trendsetter", 150),
                ("Headliner", 300), ("Star", 500), ("Sensation", 1000), ("Visionary", 2000), ("Phenomenon", 5000)]

# 預設值（之後會記住你改過的值）
DEFAULT_SETTINGS = {
    "language": "auto",           # "auto"（跟著 Windows）/ "zh" / "en"
    "hours_current": 0,
    "hours_parallel": 1,
    "hours_game_id": "",
    "games_current": 0,
    "games_target": 100,
    "games_buffer": 5,
    "minutes_per_game": 15,
    "variety_parallel": 1,
    "then_hours": True,
    "minimized": False,
    "auto_start": False,
    "auto_stop": False,           # 掛時數掛滿幾小時後自動停止
    "auto_stop_hours": 8.0,
    "stream_current": 0,
    "hours_pick": "all",          # 時數分頁的遊戲清單範圍
    "stream_pick": "all",         # 直播分頁的遊戲清單範圍
}

GREEN, RED, GRAY = "#1a7f37", "#cf222e", "#6e7781"
CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)   # 執行命令時不要跳出黑色視窗


def get_data_dir() -> Path:
    """資料都放在 %LOCALAPPDATA%\\DiscordBadgeIdler（純英文路徑，比較不會出問題）。"""
    custom = os.environ.get("BADGE_IDLER_DATA")      # 測試用，可以指定別的資料夾
    if custom:
        return Path(custom)
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    return Path(base) / "DiscordBadgeIdler"


DATA_DIR = get_data_dir()
GAMES_DIR = DATA_DIR / "games"        # 假遊戲 exe 放這裡：games\<遊戲ID>\<exe 路徑>
RUNNER_DIR = DATA_DIR / "runner"      # 編譯好的假遊戲執行器
CACHE_FILE = DATA_DIR / "detectable.json"
SOURCE_FILE = DATA_DIR / "detectable_source.txt"   # 快取的清單是從哪個網址下載的
KNOWN_FILE = DATA_DIR / "known_games.json"         # 看過的所有遊戲 ID，用來找出新遊戲
STATE_FILE = DATA_DIR / "state.json"
LOG_FILE = DATA_DIR / "log.txt"


# ============================================================================
# 語言（中文／English）：所有畫面上的文字都在這裡，每一項是 (中文, 英文)
# ============================================================================

LANGUAGES = ("zh", "en")
LANGUAGE_CHOICES = ("auto", "zh", "en")
LANGUAGE_LABELS = ("Auto / 自動", "繁體中文", "English")

STRINGS = {
    # ---- 共用 ----
    "app_name": ("Discord 徽章掛機助手", "Discord Badge Idler"),
    "sep": ("、", ", "),
    "dur_hm": ("{h} 小時 {m} 分", "{h} h {m} min"),
    "dur_h": ("{h} 小時", "{h} h"),
    "dur_m": ("{m} 分鐘", "{m} min"),
    "need_tkinter": ("你的 Python 沒有 tkinter（圖形介面模組）。\n"
                     "請到 python.org 重新安裝 Python，安裝時勾選「tcl/tk and IDLE」。",
                     "Your Python doesn't include tkinter (the GUI module).\n"
                     "Reinstall Python from python.org and tick \"tcl/tk and IDLE\"."),
    "windows_only": ("這個程式只能在 Windows 上執行。", "This app only runs on Windows."),
    "already_running": ("程式已經在執行了，請看一下工作列。", "The app is already running. Check your taskbar."),

    # ---- 遊戲清單 ----
    "list_format_bad": ("遊戲清單的格式不正確", "The game list has an unexpected format"),
    "dl_list": ("下載遊戲清單：{url}", "Downloading the game list: {url}"),
    "list_invalid": ("清單內容不正確", "The list content looks wrong"),
    "dl_failed": ("下載失敗：{error}", "Download failed: {error}"),
    "dl_no_cache": ("沒辦法下載 Discord 的遊戲清單。\n請確認網路正常，再按「重新下載清單」。",
                    "Couldn't download Discord's game list.\n"
                    "Check your internet connection, then click \"Reload list\"."),
    "using_cache": ("改用之前下載的遊戲清單。", "Using the previously downloaded game list."),
    "no_usable_games": ("遊戲清單裡找不到可以用的遊戲。", "No usable games were found in the list."),

    # ---- 假遊戲執行器 ----
    "csc_missing": ("找不到 Windows 內建的 C# 編譯器 (csc.exe)。\n"
                    "請確認電腦有 .NET Framework 4（Windows 10/11 預設就有），或改用 exe 版。",
                    "Couldn't find the C# compiler that ships with Windows (csc.exe).\n"
                    "Make sure .NET Framework 4 is installed (it is by default on Windows 10/11), "
                    "or use the EXE build."),
    "runner_from_bundle": ("使用程式內附的假遊戲執行器。", "Using the dummy game runner bundled with the app."),
    "ask_open_dotnet": ("要開啟 .NET Framework 4.8 的下載頁面嗎？", "Open the .NET Framework 4.8 download page?"),
    "fatal_error": ("程式發生錯誤，沒辦法繼續執行：\n\n{error}\n\n詳細內容存在：{path}",
                    "The app hit an error and can't continue:\n\n{error}\n\nDetails were saved to: {path}"),
    "compiling": ("第一次使用：正在編譯假遊戲執行器…", "First run: compiling the dummy game runner…"),
    "compile_failed": ("編譯假遊戲執行器失敗：\n{output}", "Failed to compile the dummy game runner:\n{output}"),
    "compiled": ("假遊戲執行器編譯完成。", "Dummy game runner compiled."),
    "runner_hint": ("請從主程式按「停止」來結束", "Use Stop in the main app to end"),
    "unsafe_path": ("不安全的路徑：{exe}", "Unsafe path: {exe}"),
    "err_av": ("{error}（可能被防毒軟體擋下或隔離了）", "{error} (probably blocked or quarantined by antivirus)"),
    "err_policy": ("{error}（被 Windows 的安全性設定擋下，例如 Smart App Control 或群組原則）",
                   "{error} (blocked by a Windows security setting such as Smart App Control or Group Policy)"),
    "err_locked": ("{error}（檔案被鎖住或沒有權限，可能是防毒軟體正在掃描）",
                   "{error} (the file is locked or access was denied; antivirus may be scanning it)"),

    # ---- 掛機紀錄 ----
    "runner_missing": ("找不到假遊戲執行器（可能被防毒軟體刪掉了），請關掉程式再重新開啟。",
                       "The dummy game runner is missing (antivirus may have deleted it). "
                       "Close and reopen the app."),
    "launch_failed": ("無法啟動「{name}」：{error}", "Couldn't start \"{name}\": {error}"),
    "now_playing": ("開始假裝在玩：{name}", "Now pretending to play: {name}"),
    "none_started": ("沒有任何假遊戲成功啟動，請看上面的錯誤訊息。",
                     "No dummy game could be started. See the errors above."),
    "hours_started": ("開始掛時數（同時 {count} 款）。", "Hours mode started ({count} at once)."),
    "marked_bad": ("「{name}」標記為偵測不到，換一款。",
                   "Marked \"{name}\" as not detected; switching to another game."),
    "no_more_games": ("沒有其他遊戲可以換了。", "There are no other games left to switch to."),
    "no_unplayed": ("找不到還沒開過的遊戲了，可以在「遊戲款數」分頁清除紀錄。",
                    "No never-opened games are left. You can clear the history on the Games played tab."),
    "only_n_left": ("可以用的新遊戲只剩 {count} 款。", "Only {count} new games are available."),
    "variety_started": ("開始跑款數：共 {total} 款，每款 {duration}，同時 {parallel} 款。",
                        "Games-played mode started: {total} games, {duration} each, {parallel} at once."),
    "too_many_failures": ("連續好幾款都無法啟動，先停止。請看上面的錯誤訊息。",
                          "Several games in a row failed to start, so it stopped. See the errors above."),
    "variety_finished": ("款數模式完成！成功 {done} 款，跳過 {skipped} 款。",
                         "Games-played mode finished! {done} done, {skipped} skipped."),
    "switch_to_hours": ("自動切換到時數模式。", "Switching to hours mode automatically."),
    "last_summary": ("上次跑款數：完成 {done} 款，跳過 {skipped} 款。",
                     "Last games-played run: {done} done, {skipped} skipped."),
    "stopped_all": ("已停止所有假遊戲。", "Stopped all dummy games."),
    "user_closed": ("你關掉了「{name}」的視窗，這款先不玩了。",
                    "You closed the \"{name}\" window, so that game was dropped."),
    "crash_loop": ("「{name}」一直意外結束，跳過這款。", "\"{name}\" keeps exiting unexpectedly; skipping it."),
    "restarted": ("「{name}」意外結束了，已重新啟動。", "\"{name}\" exited unexpectedly and was restarted."),
    "restart_failed": ("無法重新啟動「{name}」：{error}", "Couldn't restart \"{name}\": {error}"),
    "game_done": ("完成第 {count} 款：{name}", "Finished game #{count}: {name}"),
    "hours_stopped_empty": ("沒有假遊戲在執行了，時數模式已停止。",
                            "No dummy games are running anymore, so hours mode stopped."),
    "auto_stop_set": ("再掛 {time}後會自動停止。", "Hours mode will stop automatically after {time} more of idling."),
    "auto_stop_off": ("已取消自動停止。", "Auto-stop is off."),
    "auto_stopped": ("設定的 {time}掛滿了，自動停止。", "The {time} you set is up, so hours mode stopped automatically."),
    "no_new_games_fallback": ("沒有可以用的新遊戲，改從全部遊戲裡挑。",
                              "No new games are available, so picking from all games instead."),

    # ---- 遊戲選擇 ----
    "search_label": ("搜尋遊戲：", "Search games:"),
    "random_pick": ("隨機挑一款", "Pick random"),
    "list_loading": ("遊戲清單載入中…", "Loading the game list…"),
    "picked": ("已選：{name}（假程式名稱：{exe}）", "Selected: {name} (dummy file: {exe})"),
    "search_count": ("符合條件的遊戲：{count}{more} 款。沒選的話會從這些裡面隨機挑。",
                     "{count}{more} matching games. If you don't pick one, a random one from these is used."),
    "filter_label": ("範圍：", "Show:"),
    "filter_all": ("全部遊戲", "All games"),
    "filter_opened": ("只看開過的", "Opened before"),
    "filter_unopened": ("只看沒開過的", "Never opened"),
    "filter_new": ("只看新遊戲", "New games"),
    "only_n_matched": ("符合條件的遊戲只有 {count} 款。", "Only {count} games match the filter."),
    "no_match": ("沒有符合條件的遊戲可以挑，可以把範圍改成「全部遊戲」。",
                 "No games match the filter. Try switching to \"All games\"."),

    # ---- 上方狀態列 ----
    "discord_checking": ("Discord：檢查中…", "Discord: checking…"),
    "discord_running": ("Discord：● 執行中", "Discord: ● running"),
    "discord_not_running": ("Discord：● 沒有開啟（假遊戲不會被記錄）",
                            "Discord: ● not running (dummy games won't be counted)"),
    "discord_unknown": ("Discord：● 無法判斷", "Discord: ● unknown"),
    "runner_preparing": ("假遊戲執行器：準備中…", "Dummy game runner: preparing…"),
    "runner_ready": ("假遊戲執行器：● 已就緒", "Dummy game runner: ● ready"),
    "runner_failed_short": ("假遊戲執行器：● 建立失敗", "Dummy game runner: ● failed"),
    "library_loading": ("遊戲清單：載入中…", "Game list: loading…"),
    "library_loaded": ("遊戲清單：Discord 共 {total:,} 款，可以模擬的有 {usable:,} 款",
                       "Game list: {total:,} games on Discord, {usable:,} can be simulated"),
    "library_failed_short": ("遊戲清單：● 載入失敗", "Game list: ● failed to load"),
    "reload_list": ("重新下載清單", "Reload list"),
    "stop_all": ("全部停止", "Stop all"),
    "log_title": ("紀錄", "Log"),
    "status_idle": ("目前狀態：待機中", "Status: idle"),
    "status_hours": ("目前狀態：掛時數中（{count} 款）｜本次 {time}",
                     "Status: hours mode ({count} running) | this session {time}"),
    "status_variety": ("目前狀態：跑款數中（完成 {done}／{total}）｜本次 {time}",
                       "Status: games-played mode ({done}/{total} done) | this session {time}"),
    "status_auto_stop": ("｜{time}後自動停止", " | stops in {time}"),
    "status_paused": ("｜Discord 沒開，暫停計時", " | Discord isn't running, timer paused"),
    "status_streaming": ("｜直播視窗開啟中", " | stream window open"),
    "total_idle": ("這個程式累計掛機：{hours:.1f} 小時（只算 Discord 有開的時間）",
                   "Total idled by this app: {hours:.1f} h (only while Discord was running)"),

    # ---- 分頁 ----
    "tab_hours": ("遊戲時數", "Game hours"),
    "tab_variety": ("遊戲款數", "Games played"),
    "tab_stream": ("直播", "Streaming"),
    "tab_help": ("說明", "Help"),

    # ---- 遊戲時數分頁 ----
    "hours_intro": ("持續執行假遊戲，讓 Discord 累積「遊玩時數」（UNSHAKEABLE → Eternal 需要 5,000 小時）。"
                    "電腦要保持開機、Discord 要開著。",
                    "Keeps a dummy game running so Discord adds to your play time "
                    "(UNSHAKEABLE → Eternal needs 5,000 hours). Keep the PC on and Discord open."),
    "parallel_label": ("同時執行（實驗）：", "Run at once (experimental):"),
    "games_unit": ("款", "games"),
    "minimize_windows": ("假遊戲視窗縮到最小", "Minimize dummy game windows"),
    "hours_current_label": ("Discord 上目前的遊戲時數：", "Current game hours on Discord:"),
    "boot_start": ("開機時自動開啟這個程式", "Open this app when Windows starts"),
    "auto_start": ("程式開啟後自動開始掛時數", "Start hours mode when the app opens"),
    "auto_stop_label": ("掛滿", "Stop automatically after"),
    "auto_stop_unit": ("小時後自動停止（Discord 沒開的時間不算）",
                       "hours of idling (time with Discord closed doesn't count)"),
    "start_hours": ("開始掛時數", "Start hours mode"),
    "stop_hours": ("停止掛時數", "Stop hours mode"),
    "swap_game": ("Discord 沒偵測到？換一款", "Not detected by Discord? Switch game"),
    "running_list": ("執行中：{names}", "Running: {names}"),
    "hours_calc": ("→ 下一級 {tier}（{need:,} 小時）還差 {left:,} 小時，24 小時掛機約 {days:.1f} 天",
                   "→ Next: {tier} ({need:,} h), {left:,} h to go, about {days:.1f} days running 24/7"),
    "hours_max": ("→ 已經是最高等級 Eternal 了！", "→ You're already at the top tier, Eternal!"),

    # ---- 遊戲款數分頁 ----
    "variety_intro": ("自動輪流執行「沒開過」的遊戲，每款玩幾分鐘就換下一款。"
                      "MAVERICK 60 款 → Polymath 80 款 → Universalist 100 款以上。",
                      "Cycles through games the app has never opened, a few minutes each. "
                      "MAVERICK 60 games → Polymath 80 → Universalist 100+."),
    "games_current_label": ("Discord 上目前已玩款數：", "Games played on Discord now:"),
    "games_target_label": ("目標款數：", "Target:"),
    "games_buffer_label": ("多跑幾款當備用（有些可能不會被計入）：", "Extra games as a buffer (some may not count):"),
    "minutes_label": ("每款玩幾分鐘：", "Minutes per game:"),
    "variety_parallel_label": ("同時執行幾款（實驗）：", "Games at once (experimental):"),
    "then_hours": ("全部跑完後，自動切換到「遊戲時數」模式繼續掛（用時數分頁的設定）",
                   "When finished, switch to hours mode automatically (using the Game hours tab settings)"),
    "start_variety": ("開始跑款數", "Start games-played mode"),
    "stop_variety": ("停止跑款數", "Stop games-played mode"),
    "clear_played": ("清除「開過」紀錄", "Clear opened history"),
    "tier_games": ("{tier}（{count} 款）", "{tier} ({count} games)"),
    "games_max": ("已經是最高等級了", "already at the top tier"),
    "variety_plan": ("會執行 {total} 款（還差 {need} 款＋備用 {buffer} 款），大約需要 {duration}。\n"
                     "接下來的等級：{tiers}",
                     "Will run {total} games ({need} needed + {buffer} buffer), about {duration}.\n"
                     "Next tiers: {tiers}"),
    "variety_plan_done": ("目前款數已經達到目標。接下來的等級：{tiers}",
                          "You've already reached the target. Next tiers: {tiers}"),
    "variety_part": ("{name}（剩 {time}）", "{name} ({time} left)"),
    "variety_info": ("目前：{parts}\n完成 {done} 款、跳過 {skipped} 款、還有 {queued} 款排隊｜預計還要 {eta}",
                     "Now: {parts}\n{done} done, {skipped} skipped, {queued} queued | about {eta} left"),
    "played_count": ("已記錄開過 {count} 款（款數模式不會再挑這些）。",
                     "{count} games recorded as opened (games-played mode won't pick them again)."),

    # ---- 直播分頁 ----
    "stream_intro": ("「直播給他人」的時數一定要有人在看才會累積，這個程式沒辦法假造觀眾。\n"
                     "1. 選一款遊戲，按「開啟直播視窗」。\n"
                     "2. 在 Discord 語音頻道按「分享你的螢幕」，選這個視窗開始直播。\n"
                     "3. 請朋友，或用你自己的另一個帳號（例如手機）進同一個語音頻道，點開直播觀看。",
                     "Hours \"streamed to others\" only count while someone is actually watching; "
                     "this app can't fake viewers.\n"
                     "1. Pick a game and click \"Open stream window\".\n"
                     "2. In a Discord voice channel, click \"Share Your Screen\" and pick that window.\n"
                     "3. Have a friend, or your own second account (for example on your phone), "
                     "join the same voice channel and open the stream."),
    "stream_current_label": ("Discord 上目前的直播時數：", "Current streaming hours on Discord:"),
    "stream_calc": ("→ 下一級 {tier}（{need:,} 小時）還差 {left:,} 小時「有人在看」的直播",
                    "→ Next: {tier} ({need:,} h), {left:,} more hours of streaming with viewers"),
    "stream_max": ("→ 已經是最高等級 Phenomenon 了！", "→ You're already at the top tier, Phenomenon!"),
    "open_stream": ("開啟直播視窗", "Open stream window"),
    "close_stream": ("關閉直播視窗", "Close stream window"),
    "stream_open_info": ("直播視窗開啟中：{name}", "Stream window open: {name}"),
    "stream_closed_info": ("直播視窗：未開啟", "Stream window: not open"),

    # ---- 說明分頁 ----
    "open_folder": ("開啟資料夾", "Open data folder"),
    "clear_bad": ("清除「偵測不到」名單", "Clear \"not detected\" list"),
    "delete_files": ("刪除所有假遊戲檔案", "Delete all dummy game files"),
    "help_text": (
        """【第一次使用】
1. 打開 Discord 電腦版並保持登入。
2. 到「遊戲時數」分頁按「開始掛時數」（沒選遊戲會隨機挑一款）。
3. 等大約 30 秒，確認 Discord 有偵測到：
   ・看自己頭像下方的狀態，有沒有顯示「正在玩 某某遊戲」；或
   ・Discord 設定 →「已登錄的遊戲」(Registered Games)，最上面會顯示目前偵測到的遊戲。
4. 有顯示就成功了。沒有的話按「Discord 沒偵測到？換一款」。

【三種徽章】
・遊戲時數：假遊戲在跑、Discord 開著，掛 1 小時就是 1 小時，沒辦法加速。
・遊戲款數：每款預設跑 15 分鐘就換下一款。開過的遊戲都會記下來，款數模式只挑沒開過的。
・遊戲清單的「範圍」可以切換：全部遊戲／只看開過的／只看沒開過的／只看新遊戲，隨機挑選也會照這個範圍。
・遊戲清單每天會自動更新。Discord 新增遊戲時程式會通知你，新遊戲前面有 ★（{days} 天內）。
・直播時數：一定要有人在看才會算，這個程式只提供可以拿來直播的假遊戲視窗。

【小提醒】
・掛機時程式會阻止電腦「自動」睡眠（螢幕還是會關）。手動睡眠、闔上筆電或關機就會中斷。
・時數分頁可以勾「掛滿 N 小時後自動停止」，時間到就會自己停（Discord 沒開的時間不算；
  掛到一半才勾選或修改的話，從那時候開始倒數）。
・徽章進度不一定即時更新，可能要過一段時間（甚至一天）才會變。
・如果徽章一直沒增加，可以到 Discord 設定的「活動隱私」，確認有開啟分享偵測到的活動。
・Discord 隨時可能改變偵測方式，不保證一定會被計入。
・這樣做可能違反 Discord 服務條款，最壞可能被重置徽章或處分帳號，請自行承擔風險。
・關掉這個程式，所有假遊戲都會一起停止。

【假遊戲是什麼？】
第一次開啟時，程式會用 Windows 內建的 C# 編譯器 (csc.exe) 做出一個很小的視窗程式，
再把它複製成遊戲的執行檔名稱（例如 xxx.exe）來執行。Discord 看到同名的程式在跑，
就會以為你在玩那款遊戲。這些檔案不是真的遊戲、不會連網，隨時可以刪除。
存放位置：{data_dir}

【實驗功能：同時執行多款】
同時開好幾款假遊戲。如果 Discord 是分開計算每款遊戲的時數，時數會累積得比較快；
但也可能只算一份。建議先開 2～3 款掛一天，再看徽章時數有沒有多增加，再決定要不要繼續用。
""",
        """GETTING STARTED
1. Open the Discord desktop app and stay signed in.
2. On the "Game hours" tab, click "Start hours mode" (a random game is used if you don't pick one).
3. Wait about 30 seconds and check that Discord detects it:
   • your status under your avatar shows "Playing <game>", or
   • Discord Settings → Registered Games shows the detected game at the top.
4. If it does, you're set. If not, click "Not detected by Discord? Switch game".

THE THREE BADGES
• Game hours: with a dummy game running and Discord open, 1 hour idled is 1 hour. It can't be sped up.
• Games played: by default each game runs 15 minutes, then the next one starts.
  Every game the app opens is remembered, and this mode only picks games it has never opened.
• The game list's "Show" menu switches between all games, games opened before, games never
  opened, and new games. Random picks follow that choice.
• The game list updates itself every day. When Discord adds games, the app tells you, and new
  games are marked with ★ for {days} days.
• Streaming: only counts while someone is actually watching. This app only provides a window you can stream.

GOOD TO KNOW
• While idling, the app stops Windows from going to sleep on its own (the screen can still turn off).
  Manual sleep, closing a laptop lid, or shutting down will interrupt it.
• On the Game hours tab, "Stop automatically after N hours of idling" stops hours mode by itself
  when the time is up. Time with Discord closed doesn't count. If you turn it on or change it while
  hours mode is running, the countdown starts from that moment.
• Badge progress may not update right away; it can take a while (even a day).
• If a badge never goes up, check Discord Settings → Activity Privacy and make sure
  sharing your detected activity is turned on.
• Discord can change how detection works at any time, so there's no guarantee it counts.
• This may violate Discord's Terms of Service. In the worst case your badges could be reset
  or your account actioned. Use at your own risk.
• Closing this app stops all dummy games.

WHAT IS A "DUMMY GAME"?
On first launch, the app uses the C# compiler that comes with Windows (csc.exe) to build a tiny
window program, then copies it under a game's executable name (for example xxx.exe) and runs it.
Discord sees a program with that name and thinks you're playing that game. These files aren't
real games, never go online, and can be deleted at any time.
Location: {data_dir}

EXPERIMENTAL: RUNNING SEVERAL AT ONCE
Runs several dummy games at the same time. If Discord counts each game's time separately, hours add
up faster; it may also count only once. Try 2-3 games for a day, check whether your badge hours went
up more than usual, then decide.
"""),

    # ---- 對話框與紀錄 ----
    "started_app": ("{app} v{version} 啟動。資料夾：{folder}", "{app} v{version} started. Data folder: {folder}"),
    "language_changed": ("已切換成中文介面。", "Switched the interface to English."),
    "error_occurred": ("發生錯誤：{error}", "An error occurred: {error}"),
    "error_dialog": ("發生錯誤：\n{error}\n\n詳細內容寫在：{path}",
                     "An error occurred:\n{error}\n\nDetails were written to: {path}"),
    "event_error": ("處理事件時發生錯誤：{error}", "Error while handling an event: {error}"),
    "internal_error": ("內部錯誤：{error}", "Internal error: {error}"),
    "runner_failed": ("假遊戲執行器建立失敗：\n\n{error}", "Couldn't set up the dummy game runner:\n\n{error}"),
    "runner_failed_log": ("假遊戲執行器建立失敗：{error}", "Couldn't set up the dummy game runner: {error}"),
    "library_ready_log": ("遊戲清單載入完成，可以模擬的有 {count:,} 款。",
                          "Game list loaded: {count:,} games can be simulated."),
    "library_failed_log": ("遊戲清單載入失敗：{error}", "Failed to load the game list: {error}"),
    "list_auto_refresh": ("遊戲清單超過一天沒更新了，自動重新下載。",
                          "The game list is over a day old, so it's being downloaded again."),
    "new_games_log": ("Discord 新增了 {count} 款可以掛的遊戲：{names}",
                      "Discord added {count} new games you can idle: {names}"),
    "new_games_dialog": ("Discord 新增了 {count} 款可以掛的遊戲：\n\n{names}\n\n"
                         "新遊戲在清單裡前面會有 ★（{days} 天內都算新的）。\n"
                         "要在「遊戲時數」的清單裡只顯示新遊戲嗎？",
                         "Discord added {count} new games you can idle:\n\n{names}\n\n"
                         "New games are marked with ★ in the list for {days} days.\n"
                         "Show only the new games in the Game hours list?"),
    "and_more": ("…還有 {count} 款", "…and {count} more"),
    "auto_starting": ("依照設定，自動開始掛時數。", "Starting hours mode automatically (as set)."),
    "stream_window_closed": ("直播視窗被關閉了。", "The stream window was closed."),
    "runner_not_ready": ("假遊戲執行器還在準備中，請稍等幾秒。",
                         "The dummy game runner is still being prepared. Please wait a few seconds."),
    "library_not_ready": ("遊戲清單還沒載入好，請稍等。", "The game list is still loading. Please wait."),
    "open_discord": ("開啟 Discord", "Open Discord"),
    "discord_launching": ("正在開啟 Discord…", "Opening Discord…"),
    "discord_launch_failed": ("沒辦法開啟 Discord：{error}", "Couldn't open Discord: {error}"),
    "discord_not_installed": ("這台電腦好像沒有安裝 Discord 電腦版。\n要開啟 Discord 的下載頁面嗎？",
                              "The Discord desktop app doesn't seem to be installed.\n"
                              "Open the Discord download page?"),
    "ask_launch_discord": ("Discord 沒有開，假遊戲不會被記錄。\n要幫你開啟 Discord 嗎？\n\n"
                           "是：開啟 Discord 並開始\n否：直接開始\n取消：先不要開始",
                           "Discord isn't running, so dummy games won't be counted.\nOpen Discord for you?\n\n"
                           "Yes: open Discord and start\nNo: start anyway\nCancel: don't start yet"),
    "ask_open_discord_now": ("要現在幫你開啟 Discord 嗎？", "Open Discord now?"),
    "check_fix": ("檢查並修復", "Check & repair"),
    "checking": ("正在檢查並修復…", "Checking and repairing…"),
    "check_title": ("檢查結果", "Check results"),
    "check_all_ok": ("全部正常！", "Everything looks good!"),
    "chk_app": ("程式：{detail}", "App: {detail}"),
    "chk_app_exe": ("exe 版（不需要另外安裝 Python）", "EXE build (no separate Python needed)"),
    "chk_app_py": ("Python {version}，tkinter 正常", "Python {version}, tkinter OK"),
    "chk_folder_ok": ("資料夾可以寫入", "The data folder is writable"),
    "chk_folder_fail": ("資料夾沒辦法寫入：{error}", "Can't write to the data folder: {error}"),
    "chk_runner_ok": ("假遊戲執行器正常", "Dummy game runner OK"),
    "chk_runner_fixed": ("假遊戲執行器原本不見了，已經重新建立", "The dummy game runner was missing and has been rebuilt"),
    "chk_runner_fail": ("假遊戲執行器建立失敗：{error}", "Couldn't build the dummy game runner: {error}"),
    "chk_launch_ok": ("試跑假遊戲成功（沒有被防毒擋下）", "Test launch of a dummy game worked (not blocked by antivirus)"),
    "chk_launch_fail": ("試跑假遊戲失敗：{error}", "Test launch of a dummy game failed: {error}"),
    "chk_list_ok": ("遊戲清單正常（{count:,} 款）", "Game list OK ({count:,} games)"),
    "chk_list_fixed": ("遊戲清單原本沒載入，已經重新下載（{count:,} 款）",
                       "The game list wasn't loaded; downloaded it again ({count:,} games)"),
    "chk_list_fail": ("遊戲清單載入失敗：{error}", "Couldn't load the game list: {error}"),
    "chk_discord_running": ("Discord 正在執行", "Discord is running"),
    "chk_discord_closed": ("Discord 有安裝，但現在沒有開", "Discord is installed but not running"),
    "chk_discord_missing": ("找不到 Discord 電腦版", "The Discord desktop app wasn't found"),
    "chk_discord_unknown": ("沒辦法判斷 Discord 有沒有開", "Couldn't tell whether Discord is running"),
    "self_test_title": ("自我測試", "Self test"),
    "confirm_no_discord": ("沒有偵測到 Discord 在執行，假遊戲不會被記錄。\n"
                           "（Discord 沒開的時候程式會暫停計時）\n\n還是要開始嗎？",
                           "Discord doesn't seem to be running, so dummy games won't be counted.\n"
                           "(The timer pauses while Discord is closed.)\n\nStart anyway?"),
    "confirm_stop_variety": ("正在跑款數，要停止並改成掛時數嗎？",
                             "Games-played mode is running. Stop it and switch to hours mode?"),
    "start_hours_first": ("請先按「開始掛時數」。", "Click \"Start hours mode\" first."),
    "target_reached": ("目前款數已經達到目標了，可以把「目標款數」調高。",
                       "You've already reached the target. Raise the target to keep going."),
    "confirm_stop_hours": ("正在掛時數，要停止並改成跑款數嗎？\n（跑款數的時候一樣會累積時數）",
                           "Hours mode is running. Stop it and switch to games-played mode?\n"
                           "(Hours still add up during games-played mode.)"),
    "no_played": ("目前沒有「開過」的紀錄。", "There's no opened history yet."),
    "confirm_clear_played": ("要清除 {count} 款「開過」紀錄嗎？\n清除後款數模式可能會重複挑到這些遊戲。",
                             "Clear the opened history for {count} games?\n"
                             "Games-played mode may pick them again afterwards."),
    "cleared_played": ("已清除「開過」紀錄。", "Cleared the opened history."),
    "bad_empty": ("「偵測不到」名單是空的。", "The \"not detected\" list is empty."),
    "confirm_clear_bad": ("要清除 {count} 款「偵測不到」的遊戲名單嗎？",
                          "Clear {count} games from the \"not detected\" list?"),
    "cleared_bad": ("已清除「偵測不到」名單。", "Cleared the \"not detected\" list."),
    "stream_already_open": ("直播視窗已經開著了。", "The stream window is already open."),
    "stream_open_failed": ("無法開啟直播視窗：{error}", "Couldn't open the stream window: {error}"),
    "stream_opened": ("已開啟直播視窗：{name}。到 Discord 語音頻道按「分享你的螢幕」選這個視窗。",
                      "Opened the stream window: {name}. In a Discord voice channel, "
                      "click \"Share Your Screen\" and pick this window."),
    "stream_closed_log": ("已關閉直播視窗。", "Closed the stream window."),
    "boot_on": ("已設定開機時自動開啟。", "The app will now open when Windows starts."),
    "boot_off": ("已取消開機自動開啟。", "The app will no longer open when Windows starts."),
    "setting_failed": ("設定失敗：{error}", "Couldn't change the setting: {error}"),
    "suggest_auto_start": ("要不要順便勾選「程式開啟後自動開始掛時數」？\n這樣電腦重開機後會自動繼續掛。",
                           "Also turn on \"Start hours mode when the app opens\"?\n"
                           "Then idling resumes by itself after the PC restarts."),
    "stop_first": ("請先按「全部停止」。", "Click \"Stop all\" first."),
    "confirm_delete_files": ("要刪除所有假遊戲檔案嗎？\n（下次掛機時會自動重新建立）",
                             "Delete all dummy game files?\n(They're recreated automatically next time.)"),
    "deleted_files": ("已刪除所有假遊戲檔案。", "Deleted all dummy game files."),
    "confirm_close": ("還在掛機中，關閉程式會停止所有假遊戲。\n確定要關閉嗎？",
                      "Idling is still running. Closing the app stops all dummy games.\nClose anyway?"),
}

_current_language = "en"


def detect_language() -> str:
    """依照 Windows 的顯示語言決定：中文 → zh，其他 → en。"""
    forced = os.environ.get("BADGE_IDLER_LANG")      # 測試用
    if forced in LANGUAGES:
        return forced
    if os.name == "nt":
        try:
            lang_id = ctypes.windll.kernel32.GetUserDefaultUILanguage()
            return "zh" if (lang_id & 0x3FF) == 0x04 else "en"     # 0x04 = 中文
        except Exception:
            pass
    try:
        import locale
        name = (locale.getlocale()[0] or "").lower()
    except Exception:
        name = ""
    return "zh" if name.startswith(("zh", "chinese")) else "en"


def resolve_language(choice: str) -> str:
    """設定值（auto / zh / en）→ 實際使用的語言。"""
    return choice if choice in LANGUAGES else detect_language()


def set_language(code: str) -> None:
    global _current_language
    _current_language = code if code in LANGUAGES else "en"


def current_language() -> str:
    return _current_language


def t(key: str, **values) -> str:
    """取得目前語言的文字。t("now_playing", name="Minecraft") → 「開始假裝在玩：Minecraft」"""
    zh, en = STRINGS[key]
    text = zh if _current_language == "zh" else en
    return text.format(**values) if values else text


set_language(detect_language())


# ============================================================================
# 小工具
# ============================================================================

def fmt_duration(seconds: float) -> str:
    """秒數 → 時:分:秒"""
    seconds = max(0, int(seconds))
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def fmt_hours_minutes(seconds: float) -> str:
    """秒數 → 「3 小時 20 分」/ "3 h 20 min" """
    total_minutes = int(math.ceil(max(0.0, seconds) / 60))
    hours, minutes = divmod(total_minutes, 60)
    if hours and minutes:
        return t("dur_hm", h=hours, m=minutes)
    if hours:
        return t("dur_h", h=hours)
    return t("dur_m", m=minutes)


def next_tier(value: int, tiers):
    """回傳下一個還沒達到的等級 (名稱, 門檻)；已經最高級回傳 None。"""
    for name, need in tiers:
        if value < need:
            return name, need
    return None


def write_log_file(line: str) -> None:
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(time.strftime("%Y-%m-%d ") + line + "\n")
    except OSError:
        pass


def rotate_log() -> None:
    """紀錄檔超過 1MB 就換一個新的。"""
    try:
        if LOG_FILE.exists() and LOG_FILE.stat().st_size > 1_000_000:
            os.replace(LOG_FILE, LOG_FILE.with_name("log.old.txt"))
    except OSError:
        pass


def decode_console(data: bytes) -> str:
    """Windows 命令輸出的編碼是「OEM 字碼頁」（台灣是 cp950）。"""
    for encoding in ("oem", "utf-8"):
        try:
            return data.decode(encoding, errors="replace")
        except LookupError:      # 非 Windows 沒有 "oem" 這個編碼
            continue
    return data.decode("latin-1")


def write_crash_log(details: str) -> Path:
    path = DATA_DIR / "crash_log.txt"
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(time.strftime("==== %Y-%m-%d %H:%M:%S ====\n") + details + "\n")
    except OSError:
        pass
    return path


def show_native_error(title: str, message: str) -> None:
    """不靠 tkinter 跳出錯誤視窗（tkinter 壞掉、或 exe 沒有黑色視窗時也看得到）。"""
    if os.name == "nt":
        try:
            ctypes.windll.user32.MessageBoxW(None, message, title, 0x10)
            return
        except Exception:
            pass
    if sys.stderr is not None:
        sys.stderr.write(message + "\n")


def bundled_file(name: str):
    """exe 版會把檔案包在程式裡，這裡找出它解開後的位置；找不到回傳 None。"""
    folders = [Path(__file__).resolve().parent]
    if getattr(sys, "_MEIPASS", None):
        folders.append(Path(sys._MEIPASS))
    for folder in folders:
        path = folder / name
        if path.is_file():
            return path
    return None


def app_executable() -> str:
    """exe 版的 exe 檔路徑。"""
    if getattr(sys, "frozen", False):                  # PyInstaller
        return sys.executable
    compiled = globals().get("__compiled__")           # Nuitka
    original = getattr(compiled, "original_argv0", None)
    return os.path.abspath(original or sys.argv[0])


# ============================================================================
# 遊戲清單
# ============================================================================

class Game:
    """清單裡的一款遊戲。exe 是小寫、用 / 分隔的路徑，例如 "bin/game.exe"。"""
    __slots__ = ("id", "name", "exe")

    def __init__(self, app_id: str, name: str, exe: str):
        self.id = app_id
        self.name = name
        self.exe = exe

    def __repr__(self) -> str:
        return f"Game({self.id!r}, {self.name!r}, {self.exe!r})"


_ID_RE = re.compile(r"\d{5,25}")
_BAD_PATH_CHARS = set('<>:"|?*')
_RESERVED_NAMES = {"con", "prn", "aux", "nul"} | {f"com{i}" for i in range(1, 10)} | {f"lpt{i}" for i in range(1, 10)}


def normalize_exe_name(raw):
    """把清單裡的 exe 名稱整理成小寫、用 / 分隔。不安全或不適合模擬的回傳 None。"""
    if not isinstance(raw, str):
        return None
    name = raw.replace("\\", "/").lower()
    if not name or name.startswith(">") or name.startswith("/"):
        return None                       # ">" 開頭代表要完整路徑比對，不適合用假程式模擬
    if len(name) > 120 or not name.endswith(".exe"):
        return None
    if any(ch in _BAD_PATH_CHARS or ord(ch) < 32 for ch in name):
        return None
    for part in name.split("/"):
        if part in ("", ".", ".."):       # 防止路徑跑到資料夾外面
            return None
        if part != part.strip() or part.endswith("."):
            return None                   # Windows 會自動刪掉結尾的空白和句點，會對不上
        if part.split(".")[0] in _RESERVED_NAMES:
            return None                   # CON、NUL 這類是 Windows 保留名稱
    return name


def match_key(raw):
    """判斷「exe 檔名會不會和別的遊戲撞名」用的 key。"""
    if not isinstance(raw, str):
        return None
    base = raw.strip().replace("\\", "/").lower().lstrip(">").rsplit("/", 1)[-1]
    for token in ("_64", ".x64", "x64", "64"):
        base = base.replace(token, "")
    return base or None


def pick_windows_exe(app: dict):
    """從一款遊戲的資料裡挑出可以模擬的 Windows 執行檔名稱。"""
    for entry in app.get("executables") or []:
        if not isinstance(entry, dict):
            continue
        if entry.get("os") != "win32" or entry.get("is_launcher") or entry.get("arguments"):
            continue                      # 只要 Windows 版、不是啟動器、不需要額外參數的
        name = normalize_exe_name(entry.get("name"))
        if name:
            return name
    return None


def clean_game_name(raw) -> str:
    text = "".join(ch if ch.isprintable() else " " for ch in str(raw))   # 換行、Tab 等換成空白
    text = re.sub(r"\s+", " ", text).strip()
    return text[:80] or "Unknown"


class GameLibrary:
    """整理好、可以拿來模擬的遊戲清單。"""

    def __init__(self, games, total_apps: int):
        self.games = sorted(games, key=lambda g: g.name.lower())
        self.by_id = {g.id: g for g in self.games}
        self.total_apps = total_apps
        self.source = ""                  # 清單是從哪個網址來的（用來判斷是不是 Discord 官方清單）

    @classmethod
    def from_raw(cls, raw, games_dir=None, max_path: int = 240) -> GameLibrary:
        if not isinstance(raw, list):
            raise ValueError(t("list_format_bad"))
        apps = [a for a in raw if isinstance(a, dict)]

        # 1) 統計每個 exe 檔名被幾款遊戲用到。撞名的不要用，不然 Discord 可能認成別款。
        key_count = {}
        for app in apps:
            keys = set()
            for entry in app.get("executables") or []:
                if isinstance(entry, dict):
                    key = match_key(entry.get("name"))
                    if key:
                        keys.add(key)
            for key in keys:
                key_count[key] = key_count.get(key, 0) + 1

        # 2) 挑出安全、名稱唯一、路徑不會太長的遊戲
        prefix_len = len(str(games_dir)) if games_dir else 0
        games, seen = [], set()
        for app in apps:
            app_id = str(app.get("id", ""))
            name = app.get("name")
            if not _ID_RE.fullmatch(app_id) or app_id in seen:
                continue
            if not isinstance(name, str) or not name.strip():
                continue
            exe = pick_windows_exe(app)
            if not exe or key_count.get(match_key(exe), 0) != 1:
                continue
            if prefix_len and prefix_len + len(app_id) + len(exe) + 2 > max_path:
                continue                  # Windows 路徑太長會出錯
            seen.add(app_id)
            games.append(Game(app_id, clean_game_name(name), exe))
        return cls(games, len(apps))

    def search(self, text: str, limit: int = 300, keep=None):
        """用名稱搜尋：開頭符合的排前面，其次是包含的。keep(game) 回傳 False 的會被排除。"""
        text = text.strip().lower()
        starts, contains = [], []
        for game in self.games:
            if keep is not None and not keep(game):
                continue
            if not text:
                starts.append(game)
                if len(starts) >= limit:
                    break
                continue
            lowered = game.name.lower()
            if lowered.startswith(text):
                starts.append(game)
            elif text in lowered:
                contains.append(game)
        return (starts + contains)[:limit]

    def pick_random(self, count: int, exclude=()):
        """隨機挑 count 款（不重複、排除 exclude 裡的遊戲 ID）。"""
        exclude = set(exclude)
        pool = [g for g in self.games if g.id not in exclude]
        return random.sample(pool, min(max(0, int(count)), len(pool)))


def download_list(url: str, timeout: float = 60) -> bytes:
    request = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36",
        "Accept": "application/json",
    })
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def remember_list_source(url: str) -> None:
    """記下快取清單是從哪個網址下載的，連同快取檔的大小和修改時間（快取被別的程式改過就對不上）。"""
    try:
        info = CACHE_FILE.stat()
        SOURCE_FILE.write_text(json.dumps({"url": url, "size": info.st_size, "mtime_ns": info.st_mtime_ns}),
                               encoding="utf-8")
    except OSError:
        pass


def cached_list_source() -> str:
    """快取清單的來源網址。快取被別的程式（例如舊版）換過、或紀錄壞掉時回傳空字串。"""
    try:
        data = json.loads(SOURCE_FILE.read_text(encoding="utf-8"))
        info = CACHE_FILE.stat()
        if data.get("size") == info.st_size and data.get("mtime_ns") == info.st_mtime_ns:
            url = data.get("url")
            return url if isinstance(url, str) else ""
    except (OSError, ValueError, TypeError, AttributeError):
        pass
    return ""


def load_library(force_download: bool = False, log=print) -> GameLibrary:
    """讀取遊戲清單：太舊或強制更新就重新下載，下載失敗就用之前存的。"""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    raw, source = None, ""
    fresh = CACHE_FILE.exists() and time.time() - CACHE_FILE.stat().st_mtime < LIST_MAX_AGE
    if force_download or not fresh:
        for url in DETECTABLE_SOURCES:
            try:
                log(t("dl_list", url=url))
                data = download_list(url)
                parsed = json.loads(data.decode("utf-8"))
                if not isinstance(parsed, list) or len(parsed) < 100:
                    raise ValueError(t("list_invalid"))
                temp = CACHE_FILE.with_suffix(".tmp")
                temp.write_bytes(data)
                os.replace(temp, CACHE_FILE)
                remember_list_source(url)
                raw, source = parsed, url
                break
            except Exception as exc:      # 網路錯誤、格式錯誤都換下一個來源
                log(t("dl_failed", error=exc))
    if raw is None:
        if not CACHE_FILE.exists():
            raise RuntimeError(t("dl_no_cache"))
        if force_download or not fresh:
            log(t("using_cache"))
        raw = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
        source = cached_list_source()
    library = GameLibrary.from_raw(raw, GAMES_DIR)
    library.source = source
    if not library.games:
        raise RuntimeError(t("no_usable_games"))
    return library


_known_lock = threading.Lock()


def find_new_games(library, path=None) -> list:
    """跟之前看過的遊戲比對，找出 Discord 新增的遊戲（回傳 Game 清單）。

    只拿 Discord 官方清單來比（備用來源的清單比較舊，比了會誤報）。
    第一次使用、或挑選規則改過時，只把目前的遊戲記下來，不算新遊戲。
    """
    if library.source != DETECTABLE_SOURCES[0]:
        return []
    path = KNOWN_FILE if path is None else path
    with _known_lock:                     # 兩個背景工作同時比對時，才不會重複通知
        try:
            text = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            text = None                   # 第一次使用
        except ValueError:
            text = ""                     # 不是正常的文字檔 → 當成壞掉
        except OSError:
            return []                     # 暫時讀不到（例如被防毒鎖住）→ 這次先不比，下次再說
        known = set()
        if text:
            try:
                data = json.loads(text)
                ids = data.get("ids")
                if data.get("rules") == GAME_RULES_VERSION and isinstance(ids, list):
                    known = {str(x) for x in ids}
            except (ValueError, TypeError, AttributeError):
                pass                      # 壞掉或規則改過 → 重新記錄，這次不通知
        current = {g.id for g in library.games}
        new_games = [g for g in library.games if g.id not in known] if known else []
        if not current <= known:          # 記下來的是「看過的全部」，Discord 暫時拿掉的遊戲回來也不會再通知
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                temp = path.with_suffix(".tmp")
                temp.write_text(json.dumps({"rules": GAME_RULES_VERSION, "ids": sorted(known | current)}),
                                encoding="utf-8")
                os.replace(temp, path)
            except OSError:
                return []                 # 記不下來就先不通知，免得之後每次都通知同一批
        return new_games


# ============================================================================
# 假遊戲執行器（C# 小程式，第一次執行時自動用 Windows 內建的 csc.exe 編譯）
# ============================================================================

RUNNER_SOURCE = r"""// Discord Badge Idler - dummy game window
// Compiled automatically by discord_badge_idler.py (C# 5 / .NET Framework 4)
using System;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Windows.Forms;

namespace BadgeIdler
{
    public class RunnerForm : Form
    {
        private readonly string gameTitle;
        private readonly string hintText;
        private readonly bool streamMode;
        private readonly DateTime startTime;
        private readonly System.Windows.Forms.Timer timer;
        private readonly Font titleFont;
        private readonly Font clockFont;
        private readonly Font hintFont;
        private readonly bool startMinimized;

        public bool ClosedByUser { get; private set; }

        [System.Runtime.InteropServices.DllImport("user32.dll", EntryPoint = "ShowWindow")]
        private static extern bool NativeShowWindow(IntPtr hWnd, int nCmdShow);

        public RunnerForm(string gameTitle, string hintText, int slot, bool streamMode, bool minimized)
        {
            this.gameTitle = gameTitle;
            this.hintText = hintText;
            this.streamMode = streamMode;
            this.startMinimized = minimized;
            this.startTime = DateTime.Now;

            Text = gameTitle;
            DoubleBuffered = true;
            ResizeRedraw = true;
            BackColor = Color.FromArgb(30, 31, 34);
            ForeColor = Color.White;

            string fontName = "Microsoft JhengHei UI";
            if (streamMode)
            {
                titleFont = new Font(fontName, 30f, FontStyle.Bold);
                clockFont = new Font(fontName, 54f, FontStyle.Regular);
                hintFont = new Font(fontName, 12f, FontStyle.Regular);
                FormBorderStyle = FormBorderStyle.Sizable;
                ClientSize = new Size(1280, 720);
                StartPosition = FormStartPosition.CenterScreen;
            }
            else
            {
                titleFont = new Font(fontName, 11f, FontStyle.Bold);
                clockFont = new Font(fontName, 18f, FontStyle.Regular);
                hintFont = new Font(fontName, 8f, FontStyle.Regular);
                FormBorderStyle = FormBorderStyle.FixedSingle;
                MaximizeBox = false;
                ClientSize = new Size(340, 110);
                StartPosition = FormStartPosition.Manual;
                Rectangle area = Screen.PrimaryScreen.WorkingArea;
                int w = Width + 8;
                int h = Height + 8;
                int perColumn = Math.Max(1, (area.Height - 8) / h);
                int columns = Math.Max(1, (area.Width - 8) / w);
                int perLayer = perColumn * columns;
                int layer = slot / perLayer;
                int index = slot % perLayer;
                int col = index / perColumn;
                int row = index % perColumn;
                int offset = (layer % 8) * 24;
                int x = Math.Max(area.Left, area.Right - w * (col + 1) - offset);
                int y = Math.Max(area.Top, area.Bottom - h * (row + 1) - offset);
                Location = new Point(x, y);
            }
            timer = new System.Windows.Forms.Timer();
            timer.Interval = streamMode ? 40 : 1000;
            timer.Tick += OnTimerTick;
            timer.Start();
        }

        protected override bool ShowWithoutActivation
        {
            get { return !streamMode; }
        }

        // Minimize with SW_SHOWMINNOACTIVE so the window that is in use keeps the focus
        protected override void OnShown(EventArgs e)
        {
            base.OnShown(e);
            if (startMinimized)
            {
                NativeShowWindow(Handle, 7);
            }
        }

        private void OnTimerTick(object sender, EventArgs e)
        {
            Invalidate();
        }

        protected override void OnFormClosing(FormClosingEventArgs e)
        {
            if (e.CloseReason == CloseReason.UserClosing || e.CloseReason == CloseReason.TaskManagerClosing)
            {
                ClosedByUser = true;
            }
            base.OnFormClosing(e);
        }

        protected override void OnPaint(PaintEventArgs e)
        {
            base.OnPaint(e);
            Graphics g = e.Graphics;
            int w = ClientSize.Width;
            int h = ClientSize.Height;
            TimeSpan t = DateTime.Now - startTime;
            string clock = string.Format("{0:00}:{1:00}:{2:00}", (int)t.TotalHours, t.Minutes, t.Seconds);

            if (streamMode)
            {
                g.SmoothingMode = SmoothingMode.AntiAlias;
                double s = t.TotalSeconds;
                for (int i = 0; i < 6; i++)
                {
                    double a = s * (0.25 + i * 0.07) + i * 1.7;
                    int r = Math.Max(20, h / 8 + i * h / 30);
                    int cx = (int)(w / 2 + Math.Cos(a) * w / 3);
                    int cy = (int)(h / 2 + Math.Sin(a * 1.3) * h / 3);
                    using (SolidBrush b = new SolidBrush(Color.FromArgb(60, 88 + i * 25, 101, 242)))
                    {
                        g.FillEllipse(b, cx - r, cy - r, r * 2, r * 2);
                    }
                }
                DrawLine(g, gameTitle, titleFont, h / 2 - 110, 70);
                DrawLine(g, clock, clockFont, h / 2 - 30, 100);
                DrawLine(g, "Discord Badge Idler", hintFont, h - 40, 30);
            }
            else
            {
                DrawLine(g, gameTitle, titleFont, 8, 28);
                DrawLine(g, clock, clockFont, 36, 40);
                DrawLine(g, hintText, hintFont, 80, 22);
            }
        }

        private void DrawLine(Graphics g, string text, Font font, int y, int height)
        {
            Rectangle rect = new Rectangle(8, y, ClientSize.Width - 16, height);
            TextRenderer.DrawText(g, text, font, rect, Color.White,
                TextFormatFlags.HorizontalCenter | TextFormatFlags.VerticalCenter |
                TextFormatFlags.SingleLine | TextFormatFlags.EndEllipsis | TextFormatFlags.NoPrefix);
        }

        protected override void Dispose(bool disposing)
        {
            if (disposing)
            {
                timer.Dispose();
                titleFont.Dispose();
                clockFont.Dispose();
                hintFont.Dispose();
            }
            base.Dispose(disposing);
        }

        // When the Python app exits or crashes, stdin breaks and this window closes itself (no orphans).
        private static void WatchStdin()
        {
            try
            {
                using (System.IO.Stream input = Console.OpenStandardInput())
                {
                    byte[] buffer = new byte[256];
                    while (input.Read(buffer, 0, buffer.Length) > 0)
                    {
                    }
                }
            }
            catch (Exception)
            {
            }
            Environment.Exit(0);
        }

        [STAThread]
        public static int Main(string[] args)
        {
            string title = "Game";
            string hint = "Use Stop in the main app to end";
            int slot = 0;
            bool stream = false;
            bool minimized = false;
            bool watchStdin = false;
            for (int i = 0; i < args.Length; i++)
            {
                string a = args[i];
                if (a == "--title" && i + 1 < args.Length)
                {
                    i++;
                    title = args[i];
                }
                else if (a == "--hint" && i + 1 < args.Length)
                {
                    i++;
                    hint = args[i];
                }
                else if (a == "--slot" && i + 1 < args.Length)
                {
                    i++;
                    int.TryParse(args[i], out slot);
                }
                else if (a == "--stream")
                {
                    stream = true;
                }
                else if (a == "--min")
                {
                    minimized = true;
                }
                else if (a == "--watch-stdin")
                {
                    watchStdin = true;
                }
            }
            if (slot < 0)
            {
                slot = 0;
            }

            if (watchStdin)
            {
                System.Threading.Thread watcher = new System.Threading.Thread(new System.Threading.ThreadStart(WatchStdin));
                watcher.IsBackground = true;
                watcher.Start();
            }

            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);
            RunnerForm form = new RunnerForm(title, hint, slot, stream, minimized);
            Application.Run(form);
            return form.ClosedByUser ? 2 : 0;
        }
    }
}
"""

RUNNER_VERSION = hashlib.sha1(RUNNER_SOURCE.encode("utf-8")).hexdigest()[:12]


def find_csc():
    """找 Windows 內建的 C# 編譯器（.NET Framework 4 附的，Windows 10/11 都有）。"""
    windir = os.environ.get("WINDIR", r"C:\Windows")
    for sub in ("Framework64", "Framework"):
        path = Path(windir) / "Microsoft.NET" / sub / "v4.0.30319" / "csc.exe"
        if path.is_file():
            return path
    return None


class CscMissingError(RuntimeError):
    """電腦上找不到 C# 編譯器。"""


def build_runner(log=print) -> Path:
    """準備假遊戲執行器：exe 版直接用內附的；否則用 csc 編譯。已經準備好而且版本相同就直接用。"""
    RUNNER_DIR.mkdir(parents=True, exist_ok=True)
    exe = RUNNER_DIR / "BadgeIdlerRunner.exe"
    stamp = RUNNER_DIR / "version.txt"
    if exe.is_file() and stamp.is_file() and stamp.read_text(encoding="utf-8").strip() == RUNNER_VERSION:
        return exe
    bundled = bundled_file("BadgeIdlerRunner.exe") if IS_FROZEN else None
    if bundled is not None:
        shutil.copyfile(str(bundled), str(exe))
        stamp.write_text(RUNNER_VERSION, encoding="utf-8")
        log(t("runner_from_bundle"))
        return exe
    csc = find_csc()
    if csc is None:
        raise CscMissingError(t("csc_missing"))
    log(t("compiling"))
    source = RUNNER_DIR / "BadgeIdlerRunner.cs"
    source.write_text(RUNNER_SOURCE, encoding="utf-8-sig")
    command = [str(csc), "/nologo", "/noconfig", "/target:winexe", "/optimize+", "/codepage:65001",
               "/r:System.dll", "/r:System.Drawing.dll", "/r:System.Windows.Forms.dll",
               "/out:" + str(exe), str(source)]
    result = subprocess.run(command, capture_output=True, timeout=180, creationflags=CREATE_NO_WINDOW)
    if result.returncode != 0 or not exe.is_file():
        output = decode_console(result.stdout + result.stderr).strip()
        raise RuntimeError(t("compile_failed", output=output[-1500:]))
    stamp.write_text(RUNNER_VERSION, encoding="utf-8")
    log(t("compiled"))
    return exe


# 這些 Windows 錯誤代碼代表「環境擋住了程式」（防毒、權限、安全性原則），不是遊戲本身的問題
_ENVIRONMENT_WINERRORS = {5, 32, 225, 226, 1260, 4551}


def explain_launch_error(exc) -> str:
    code = getattr(exc, "winerror", None)
    if code in (225, 226):
        return t("err_av", error=exc)
    if code in (1260, 4551):
        return t("err_policy", error=exc)
    if code in (5, 32):
        return t("err_locked", error=exc)
    return str(exc)


def fake_exe_path(game: Game, games_dir=None) -> Path:
    """假遊戲 exe 的位置：games\\<遊戲ID>\\<清單上的 exe 路徑>"""
    base = Path(games_dir) if games_dir else GAMES_DIR
    path = base.joinpath(game.id, *game.exe.split("/"))
    base_abs = os.path.abspath(str(base))
    if os.path.commonpath([base_abs, os.path.abspath(str(path))]) != base_abs:
        raise ValueError(t("unsafe_path", exe=game.exe))     # 再保險一次，路徑不能跑出資料夾
    return path


class FakeGame:
    """一個假遊戲程式（一個視窗）。"""

    def __init__(self, game: Game, runner, slot: int = 0, minimized: bool = False,
                 stream: bool = False, games_dir=None):
        self.game = game
        self.runner = Path(runner)
        self.slot = slot
        self.minimized = minimized
        self.stream = stream
        self.games_dir = games_dir
        self.proc = None
        self.play_seconds = 0.0       # Discord 開著時累積的執行時間
        self.crash_times = []         # 最近意外結束的時間，用來判斷是不是一直當掉

    @property
    def exe_path(self) -> Path:
        return fake_exe_path(self.game, self.games_dir)

    def start(self) -> None:
        path = self.exe_path
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.is_file() or not filecmp.cmp(str(self.runner), str(path), shallow=False):
            shutil.copy(str(self.runner), str(path))           # 複製成遊戲的 exe 名稱
        args = [str(path), "--title", self.game.name, "--slot", str(self.slot),
                "--hint", t("runner_hint"), "--watch-stdin"]
        if self.minimized:
            args.append("--min")
        if self.stream:
            args.append("--stream")
        self._close_pipe()
        # stdin 接一條管線：Python 這邊結束時管線會斷，假遊戲就會自己關掉
        self.proc = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                                     stderr=subprocess.DEVNULL, cwd=str(path.parent))

    def exit_code(self):
        """還在執行回傳 None；已經結束回傳結束代碼。"""
        if self.proc is None:
            return -1
        return self.proc.poll()

    def is_running(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def stop(self) -> None:
        proc = self.proc
        if proc is not None and proc.poll() is None:
            try:
                proc.terminate()
                proc.wait(timeout=3)
            except (OSError, subprocess.TimeoutExpired):
                pass
        self._close_pipe()

    def _close_pipe(self) -> None:
        if self.proc is not None and self.proc.stdin is not None:
            try:
                self.proc.stdin.close()
            except OSError:
                pass


def self_test_launch(runner, seconds: float = 2.0, games_dir=None):
    """試跑一個假遊戲幾秒鐘，確認沒有被防毒或系統擋下。成功回傳 None，失敗回傳原因。"""
    game = Game("1000000000000000000", t("self_test_title"), "selftest/badge_idler_selftest.exe")
    fake = FakeGame(game, runner, minimized=True, games_dir=games_dir)
    try:
        fake.start()
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        return explain_launch_error(exc)
    try:
        time.sleep(seconds)
        code = fake.exit_code()
        return None if code is None else f"exit code {code}"
    finally:
        fake.stop()


# ============================================================================
# 狀態存檔（玩過哪些遊戲、累計時間、設定）
# ============================================================================

class State:
    def __init__(self, path: Path):
        self.path = path
        self.played_ids = set()       # 款數模式已經跑完的遊戲
        self.opened_ids = set()       # 這個程式開過的所有遊戲（任何模式）
        self.bad_ids = set()          # 偵測不到或一直當掉的遊戲，之後不再挑
        self.new_games = {}           # Discord 新增的遊戲：遊戲 ID → 發現的時間（秒）
        self.total_seconds = 0.0      # 這個程式總共掛了多久
        self.settings = dict(DEFAULT_SETTINGS)

    def load(self) -> None:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        if not isinstance(data, dict):
            return
        self.played_ids = {str(x) for x in data.get("played_ids", []) if isinstance(x, (str, int))}
        self.bad_ids = {str(x) for x in data.get("bad_ids", []) if isinstance(x, (str, int))}
        self.opened_ids = {str(x) for x in data.get("opened_ids", []) if isinstance(x, (str, int))}
        self.opened_ids |= self.played_ids          # 舊版只有 played_ids
        try:
            self.total_seconds = float(data.get("total_seconds", 0) or 0)
        except (TypeError, ValueError):
            self.total_seconds = 0.0
        new_games = data.get("new_games")
        if isinstance(new_games, dict):
            self.new_games = {key: float(value) for key, value in new_games.items()
                              if _ID_RE.fullmatch(str(key)) and type(value) in (int, float) and math.isfinite(value)}
        self.prune_new_games()
        settings = data.get("settings")
        if isinstance(settings, dict):
            for key, default in DEFAULT_SETTINGS.items():
                value = settings.get(key, default)
                if type(value) is type(default):
                    self.settings[key] = value
        if self.settings["language"] not in LANGUAGE_CHOICES:
            self.settings["language"] = "auto"
        for key in ("hours_pick", "stream_pick"):
            if self.settings[key] not in PICK_MODES:
                self.settings[key] = "all"
        low, high = AUTO_STOP_LIMITS
        if not low <= self.settings["auto_stop_hours"] <= high:      # 超出範圍（或 NaN）就用預設
            self.settings["auto_stop_hours"] = DEFAULT_SETTINGS["auto_stop_hours"]

    def save(self) -> None:
        data = {
            "played_ids": sorted(self.played_ids),
            "bad_ids": sorted(self.bad_ids),
            "opened_ids": sorted(self.opened_ids),
            "new_games": {key: round(value) for key, value in sorted(self.new_games.items())},
            "total_seconds": round(self.total_seconds, 1),
            "settings": self.settings,
        }
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temp = self.path.with_suffix(".tmp")
            temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            os.replace(temp, self.path)
        except OSError:
            pass

    def add_new_games(self, games, now=None) -> None:
        now = time.time() if now is None else now
        for game in games:
            self.new_games.setdefault(game.id, now)
        self.prune_new_games(now)

    def prune_new_games(self, now=None) -> None:
        """發現超過 NEW_GAME_DAYS 天的遊戲就不算新遊戲了。"""
        now = time.time() if now is None else now
        limit = NEW_GAME_DAYS * 86400
        self.new_games = {key: found for key, found in self.new_games.items() if now - found < limit}


# ============================================================================
# 掛機邏輯（時數模式、款數模式）。GUI 每秒呼叫一次 tick()。
# ============================================================================

class Idler:
    def __init__(self, state: State, log):
        self.state = state
        self.log = log
        self.runner = None
        self.library = None
        self.games_dir = None             # None = 用預設的 GAMES_DIR
        self.discord_running = True       # Discord 沒開時暫停計時
        self.mode = None                  # None / "hours" / "variety"
        self.slots = []                   # 正在執行的 FakeGame
        self.parallel = 1
        self.minimized = False
        self.pick_mode = "all"            # 隨機挑遊戲的範圍：all / opened / unopened
        self.stop_after = None            # 時數模式：本次掛到第幾秒時自動停止（None = 不會自動停止）
        self.stop_limit = None            # 設定的自動停止時間長度（秒）
        self.auto_stopped = None          # 上次自動停止時設定的時間長度（給介面顯示）
        self.session_seconds = 0.0
        # 款數模式
        self.queue = []
        self.variety_total = 0
        self.variety_done = 0
        self.variety_skipped = 0
        self.variety_seconds = 900.0
        self.then_hours = None
        self.last_result = None           # 上次跑款數的結果 (完成, 跳過)
        self._launch_failures = 0
        self._last_tick = None
        self._last_save = 0.0

    @property
    def ready(self) -> bool:
        return self.runner is not None and self.library is not None

    def running_ids(self):
        return {fg.game.id for fg in self.slots}

    def pick_games(self, count: int, pick_mode: str = "all", exclude=()):
        """依照範圍（全部／開過的／沒開過的／新遊戲）隨機挑 count 款，排除 exclude 和偵測不到的遊戲。"""
        exclude = set(exclude) | self.state.bad_ids
        opened = self.state.opened_ids
        pool = []
        for game in self.library.games:
            if game.id in exclude:
                continue
            if pick_mode == "opened" and game.id not in opened:
                continue
            if pick_mode == "unopened" and game.id in opened:
                continue
            if pick_mode == "new" and game.id not in self.state.new_games:
                continue
            pool.append(game)
        return random.sample(pool, min(max(0, int(count)), len(pool)))

    def _free_slot(self) -> int:
        used = {fg.slot for fg in self.slots}
        slot = 0
        while slot in used:
            slot += 1
        return slot

    def _launch(self, game: Game, slot=None):
        if not Path(self.runner).is_file():
            self._launch_failures += 3          # 執行器不見了，再試也沒用
            self.log(t("runner_missing"))
            return None
        fake = FakeGame(game, self.runner, slot=self._free_slot() if slot is None else slot,
                        minimized=self.minimized, games_dir=self.games_dir)
        try:
            fake.start()
        except (OSError, ValueError, subprocess.SubprocessError) as exc:
            self._launch_failures += 1
            if getattr(exc, "winerror", None) not in _ENVIRONMENT_WINERRORS:
                self.state.bad_ids.add(game.id)          # 環境的問題不算這款遊戲的錯
            self.log(t("launch_failed", name=game.name, error=explain_launch_error(exc)))
            return None
        self._launch_failures = 0
        self.slots.append(fake)
        self.state.opened_ids.add(game.id)
        self.log(t("now_playing", name=game.name))
        return fake

    def _begin(self) -> None:
        self.session_seconds = 0.0
        self._last_tick = None
        self._set_awake(True)

    # ---------- 時數模式 ----------
    def start_hours(self, main_game=None, parallel: int = 1, minimized: bool = False,
                    pick_mode: str = "all", stop_after=None) -> bool:
        """stop_after：掛滿幾秒後自動停止（None = 一直掛到手動停止）。"""
        if not self.ready:
            return False
        self.stop(quiet=True)
        self.auto_stopped = None
        self.parallel = max(1, min(MAX_PARALLEL, int(parallel)))
        self.minimized = bool(minimized)
        self.pick_mode = pick_mode if pick_mode in PICK_MODES else "all"
        games = [main_game] if main_game is not None else []
        need = self.parallel - len(games)
        picks = self.pick_games(need, self.pick_mode, {g.id for g in games})
        if not games and not picks and self.pick_mode == "new":   # 新遊戲都不能用了 → 改從全部遊戲挑，才不會掛不起來
            self.log(t("no_new_games_fallback"))
            self.pick_mode = "all"
            picks = self.pick_games(need, self.pick_mode)
        if len(picks) < need:
            self.log(t("only_n_matched", count=len(picks)))
        games += picks
        if not games:
            self.log(t("no_match"))
            return False
        self.mode = "hours"
        for game in games:
            self._launch(game)
        if not self.slots:
            self.log(t("none_started"))
            self.stop(quiet=True)
            return False
        self._begin()
        self.log(t("hours_started", count=len(self.slots)))
        self.set_stop_after(stop_after)
        return True

    def set_stop_after(self, seconds) -> None:
        """設定時數模式再掛幾秒後自動停止（None 或 0 = 不自動停止）。

        從設定的這一刻開始倒數：開始掛時就是從頭算；掛到一半才勾或改，也是從那時候開始算，
        不會因為已經掛很久而一勾就停。設定沒變就什麼都不做（不會重新倒數）。
        """
        seconds = float(seconds) if seconds else None
        if seconds == self.stop_limit:
            return
        self.stop_limit = seconds
        self.stop_after = None if seconds is None else self.session_seconds + seconds
        if self.mode == "hours":
            self.log(t("auto_stop_set", time=fmt_hours_minutes(seconds)) if seconds else t("auto_stop_off"))

    def replace_main(self):
        """時數模式：目前的主要遊戲偵測不到 → 標記起來、換一款。"""
        if self.mode != "hours" or not self.slots:
            return None
        old = self.slots[0]
        old.stop()
        self.slots.remove(old)
        self.state.bad_ids.add(old.game.id)
        self.log(t("marked_bad", name=old.game.name))
        picks = self.pick_games(1, self.pick_mode, self.running_ids())
        if not picks:
            self.log(t("no_more_games"))
            return None
        fake = self._launch(picks[0], slot=old.slot)
        if fake is not None:
            self.slots.remove(fake)
            self.slots.insert(0, fake)
        return fake

    # ---------- 款數模式 ----------
    def start_variety(self, count: int, minutes: float, parallel: int = 1,
                      minimized: bool = False, then_hours=None) -> bool:
        if not self.ready:
            return False
        self.stop(quiet=True)
        self.auto_stopped = None
        picks = self.pick_games(count, "unopened", self.state.played_ids)
        if not picks:
            self.log(t("no_unplayed"))
            return False
        if len(picks) < count:
            self.log(t("only_n_left", count=len(picks)))
        self.mode = "variety"
        self.queue = list(picks)
        self.variety_total = len(picks)
        self.variety_done = 0
        self.variety_skipped = 0
        self.variety_seconds = max(1.0, float(minutes) * 60.0)
        self.parallel = max(1, min(MAX_PARALLEL, int(parallel)))
        self.minimized = bool(minimized)
        self.then_hours = then_hours
        self._launch_failures = 0
        self._begin()
        self.log(t("variety_started", total=self.variety_total,
                   duration=fmt_hours_minutes(self.variety_seconds), parallel=self.parallel))
        self._fill_variety()
        return self.mode == "variety"

    def _fill_variety(self) -> None:
        while self.mode == "variety" and len(self.slots) < self.parallel and self.queue:
            game = self.queue.pop(0)
            if self._launch(game) is None:
                self.variety_skipped += 1
                if self._launch_failures >= 3:
                    self.log(t("too_many_failures"))
                    self.stop(quiet=True)
                    return

    def _finish_variety(self) -> None:
        then = self.then_hours
        self.stop(quiet=True)              # stop() 會順便記下 last_result
        done, skipped = self.last_result
        self.log(t("variety_finished", done=done, skipped=skipped))
        if then is not None:
            self.log(t("switch_to_hours"))
            self.start_hours(then.get("game"), then.get("parallel", 1), then.get("minimized", False),
                             then.get("pick_mode", "all"), then.get("stop_after"))

    def variety_eta_seconds(self) -> float:
        if self.mode != "variety":
            return 0.0
        remaining = sum(max(0.0, self.variety_seconds - fg.play_seconds) for fg in self.slots)
        remaining += len(self.queue) * self.variety_seconds
        return remaining / max(1, self.parallel)

    # ---------- 共用 ----------
    def stop(self, quiet: bool = False) -> None:
        was_running = self.mode is not None
        if self.mode == "variety":
            self.last_result = (self.variety_done, self.variety_skipped)
        for fake in self.slots:
            fake.stop()
        self.slots = []
        self.queue = []
        self.mode = None
        self.then_hours = None
        self.stop_after = None
        self.stop_limit = None
        self._set_awake(False)
        self.state.save()
        if was_running and not quiet:
            self.log(t("stopped_all"))

    def tick(self, now=None) -> None:
        now = time.monotonic() if now is None else now
        if self.mode is None:
            self._last_tick = now
            return
        # 距離上次 tick 的秒數（最多算 5 秒，電腦睡眠回來不會多算）
        dt = 0.0 if self._last_tick is None else min(max(now - self._last_tick, 0.0), 5.0)
        self._last_tick = now
        counting = bool(self.discord_running)

        # 1) 檢查每個假遊戲還在不在
        for fake in list(self.slots):
            code = fake.exit_code()
            if code is None:
                if counting:
                    fake.play_seconds += dt
                continue
            if code == USER_CLOSED_EXIT_CODE:
                self.log(t("user_closed", name=fake.game.name))
                self._drop(fake)
                continue
            fake.crash_times = [x for x in fake.crash_times if now - x < 60] + [now]
            if len(fake.crash_times) >= 3:
                self.log(t("crash_loop", name=fake.game.name))
                self.state.bad_ids.add(fake.game.id)
                self._drop(fake)
                continue
            try:
                fake.start()
                self.log(t("restarted", name=fake.game.name))
            except (OSError, ValueError, subprocess.SubprocessError) as exc:
                self.log(t("restart_failed", name=fake.game.name, error=explain_launch_error(exc)))
                self._drop(fake)

        # 2) 累計時間（Discord 有開才算）
        if self.slots and counting:
            self.session_seconds += dt
            self.state.total_seconds += dt

        # 3) 時數模式：掛滿設定的時間就自動停止
        if self.mode == "hours" and self.stop_after is not None and self.session_seconds >= self.stop_after:
            limit = self.stop_limit
            self.stop(quiet=True)
            self.auto_stopped = limit
            self.log(t("auto_stopped", time=fmt_hours_minutes(limit)))
            return

        # 4) 款數模式：玩夠久的換下一款
        if self.mode == "variety":
            for fake in list(self.slots):
                if fake.play_seconds >= self.variety_seconds:
                    fake.stop()
                    self.slots.remove(fake)
                    self.state.played_ids.add(fake.game.id)
                    self.variety_done += 1
                    self.log(t("game_done", count=self.variety_done, name=fake.game.name))
            self._fill_variety()
            if self.mode == "variety" and not self.slots and not self.queue:
                self._finish_variety()
                return
        elif self.mode == "hours" and not self.slots:
            self.log(t("hours_stopped_empty"))
            self.stop(quiet=True)
            return

        # 5) 每分鐘存檔一次
        if now - self._last_save >= 60:
            self.state.save()
            self._last_save = now

    def _drop(self, fake: FakeGame) -> None:
        fake.stop()
        if fake in self.slots:
            self.slots.remove(fake)
        if self.mode == "variety":
            self.variety_skipped += 1

    @staticmethod
    def _set_awake(on: bool) -> None:
        """掛機時防止電腦「自動」睡眠（螢幕還是可以關）。"""
        if os.name != "nt":
            return
        try:
            set_state = ctypes.windll.kernel32.SetThreadExecutionState
            set_state.argtypes = [ctypes.c_uint32]
            set_state.restype = ctypes.c_uint32
            ES_CONTINUOUS, ES_SYSTEM_REQUIRED = 0x80000000, 0x00000001
            set_state(ES_CONTINUOUS | (ES_SYSTEM_REQUIRED if on else 0))
        except Exception:
            pass


# ============================================================================
# Windows 相關：Discord 有沒有開、開機自動啟動、只允許開一個
# ============================================================================

def is_discord_running():
    """回傳 True / False；沒辦法判斷時回傳 None。"""
    if os.name != "nt":
        return None
    try:
        output = subprocess.run(["tasklist", "/FO", "CSV", "/NH"], capture_output=True, timeout=30,
                                creationflags=CREATE_NO_WINDOW).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    text = output.decode("ascii", errors="ignore")
    if not text.strip():
        return None
    for line in text.splitlines():
        name = line.split(",", 1)[0].strip().strip('"').lower()
        if name in DISCORD_PROCESS_NAMES:
            return True
    return False


def find_discord():
    """回傳 (Update.exe 路徑, Discord 執行檔名稱)；沒安裝回傳 None。"""
    base = os.environ.get("LOCALAPPDATA")
    if not base:
        return None
    for folder, exe_name in DISCORD_INSTALLS:
        updater = Path(base) / folder / "Update.exe"
        if updater.is_file():
            return updater, exe_name
    return None


def launch_discord() -> bool:
    """開啟 Discord 電腦版。沒安裝回傳 False；開啟失敗會丟出 OSError。"""
    found = find_discord()
    if found is None:
        return False
    updater, exe_name = found
    subprocess.Popen([str(updater), "--processStart", exe_name], creationflags=CREATE_NO_WINDOW)
    return True


RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_VALUE = "DiscordBadgeIdler"


def autostart_command() -> str:
    if IS_FROZEN:
        return f'"{app_executable()}" --autostart'
    exe = Path(sys.executable)
    windowless = exe.with_name("pythonw.exe")      # 用 pythonw 開機時才不會跳出黑色視窗
    if windowless.is_file():
        exe = windowless
    return f'"{exe}" "{Path(__file__).resolve()}" --autostart'


def get_autostart() -> bool:
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            winreg.QueryValueEx(key, RUN_VALUE)
        return True
    except (ImportError, OSError):
        return False


def set_autostart(enabled: bool) -> None:
    import winreg
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
        if enabled:
            winreg.SetValueEx(key, RUN_VALUE, 0, winreg.REG_SZ, autostart_command())
        else:
            try:
                winreg.DeleteValue(key, RUN_VALUE)
            except FileNotFoundError:
                pass


_instance_mutex = None


def acquire_single_instance() -> bool:
    """同時只能開一個，避免兩個程式搶著改存檔。"""
    global _instance_mutex
    if os.name != "nt":
        return True
    try:
        from ctypes import wintypes
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
        kernel32.CreateMutexW.restype = wintypes.HANDLE
        handle = kernel32.CreateMutexW(None, False, "Local\\DiscordBadgeIdler")
        if handle and ctypes.get_last_error() == 183:      # ERROR_ALREADY_EXISTS
            return False
        _instance_mutex = handle
    except Exception:
        pass
    return True


def enable_dpi_awareness() -> None:
    """高解析度螢幕上字才不會糊。"""
    if os.name != "nt":
        return
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


# ============================================================================
# 圖形介面
# ============================================================================

_TkFrame = ttk.Frame if tk is not None else object


class GamePicker(_TkFrame):
    """搜尋框＋遊戲清單，讓使用者挑一款遊戲。"""
    MAX_SHOW = 300

    def __init__(self, master, app, height: int = 7, mode_key=None):
        super().__init__(master)
        self.app = app
        self.mode_key = mode_key          # 把「範圍」存在設定的哪個欄位
        self.shown = []
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *args: self.refresh())

        row = ttk.Frame(self)
        row.pack(fill="x")
        app.translate(ttk.Label(row), "search_label").pack(side="left")
        ttk.Entry(row, textvariable=self.search_var).pack(side="left", fill="x", expand=True, padx=4)
        app.translate(ttk.Label(row), "filter_label").pack(side="left", padx=(4, 2))
        self.cmb_filter = ttk.Combobox(row, state="readonly", width=12)
        self.cmb_filter.pack(side="left", padx=(0, 4))
        self.cmb_filter.bind("<<ComboboxSelected>>", self._on_filter_changed)
        app.translate(ttk.Button(row, command=self.pick_random), "random_pick").pack(side="left")

        box = ttk.Frame(self)
        box.pack(fill="both", expand=True, pady=(4, 0))
        self.listbox = tk.Listbox(box, height=height, exportselection=False, activestyle="none")
        bar = ttk.Scrollbar(box, orient="vertical", command=self.listbox.yview)
        self.listbox.configure(yscrollcommand=bar.set)
        self.listbox.pack(side="left", fill="both", expand=True)
        bar.pack(side="right", fill="y")
        self.listbox.bind("<<ListboxSelect>>", lambda event: self.update_hint())

        self.hint = ttk.Label(self, text=t("list_loading"), foreground=GRAY)
        self.hint.pack(anchor="w")

        saved = app.state.settings.get(mode_key, "all") if mode_key else "all"
        if saved == "new" and not app.state.new_games:     # 新遊戲都過期了 → 改回全部遊戲（開機自動掛才挑得到遊戲）
            saved = "all"
            app.state.settings[mode_key] = saved
        self.cmb_filter.configure(values=self._filter_labels())
        self.cmb_filter.current(PICK_MODES.index(saved) if saved in PICK_MODES else 0)

    @staticmethod
    def _filter_labels():
        return [t("filter_all"), t("filter_opened"), t("filter_unopened"), t("filter_new")]

    def mode(self) -> str:
        """目前的範圍：all / opened / unopened / new"""
        index = self.cmb_filter.current()
        return PICK_MODES[index] if 0 <= index < len(PICK_MODES) else "all"

    def set_mode(self, mode: str, clear_search: bool = True) -> None:
        """切換範圍。clear_search=True 會清掉搜尋文字（才看得到這個範圍的全部遊戲）；
        False 則保留搜尋文字和目前選的遊戲。"""
        keep = None if clear_search else self._selected_now()
        self.cmb_filter.current(PICK_MODES.index(mode))
        if clear_search:
            self.search_var.set("")
        if self.mode_key:
            self.app.state.settings[self.mode_key] = self.mode()
            self.app.state.save()
        self.refresh(ensure=keep)

    def update_texts(self) -> None:
        """切換語言時更新下拉選單的文字。"""
        index = self.cmb_filter.current()
        self.cmb_filter.configure(values=self._filter_labels())
        self.cmb_filter.current(index if 0 <= index < len(PICK_MODES) else 0)
        self.update_hint()

    def _on_filter_changed(self, event=None) -> None:
        if self.mode_key:
            self.app.state.settings[self.mode_key] = self.mode()
            self.app.state.save()
        self.refresh()

    def _keep(self, game: Game) -> bool:
        mode = self.mode()
        if mode == "opened":
            return game.id in self.app.state.opened_ids
        if mode == "unopened":
            return game.id not in self.app.state.opened_ids
        if mode == "new":
            return game.id in self.app.state.new_games
        return True

    def refresh(self, ensure=None) -> None:
        library = self.app.library
        self.listbox.delete(0, "end")
        self.shown = []
        if library is None:
            self.update_hint()
            return
        results = library.search(self.search_var.get(), self.MAX_SHOW, keep=self._keep)
        if ensure is not None and all(g.id != ensure.id for g in results):
            results = [ensure] + results[: self.MAX_SHOW - 1]
        self.shown = results
        opened, new_games = self.app.state.opened_ids, self.app.state.new_games
        for game in results:
            marks = (OPENED_MARK if game.id in opened else "") + (NEW_MARK if game.id in new_games else "")
            self.listbox.insert("end", marks + game.name)
        if ensure is not None:
            for index, game in enumerate(results):
                if game.id == ensure.id:
                    self.listbox.selection_clear(0, "end")
                    self.listbox.selection_set(index)
                    self.listbox.see(index)
                    break
        self.update_hint()

    def update_hint(self) -> None:
        if self.app.library is None:
            self.hint.configure(text=t("list_loading"))
            return
        game = self.selected()
        if game is not None:
            self.hint.configure(text=t("picked", name=game.name, exe=game.exe))
        else:
            more = "+" if len(self.shown) >= self.MAX_SHOW else ""
            self.hint.configure(text=t("search_count", count=len(self.shown), more=more))

    def selected(self):
        selection = self.listbox.curselection()
        if not selection:
            return None
        index = int(selection[0])
        return self.shown[index] if 0 <= index < len(self.shown) else None

    def select_game(self, game: Game) -> None:
        """選取一款遊戲（不在目前清單裡的話會放到最上面）。"""
        self.refresh(ensure=game)

    def _selected_now(self):
        """目前選的遊戲（清單重新下載過的話，換成新清單裡的同一款；新清單沒有就回傳 None）。"""
        game = self.selected()
        library = self.app.library
        if game is not None and library is not None:
            game = library.by_id.get(game.id)
        return game

    def refresh_keep(self) -> None:
        """重新整理清單（更新「開過」「新遊戲」記號），保留目前選的遊戲。"""
        self.refresh(ensure=self._selected_now())

    def pick_random(self) -> None:
        if self.app.library is None:
            return
        picks = self.app.idler.pick_games(1, self.mode())
        if picks:
            self.select_game(picks[0])
        else:
            messagebox.showinfo(t("app_name"), t("no_match"))


class App:
    def __init__(self, root, autostart: bool = False):
        self.root = root
        self.autostart = autostart
        self.events = queue.Queue()          # 背景執行緒 → 主執行緒 的訊息
        self.state = State(STATE_FILE)
        self.state.load()
        set_language(resolve_language(self.state.settings["language"]))
        self.library = None
        self.library_error = None
        self.runner = None
        self.runner_error = None
        self.discord_running = None
        self.discord_checked = False
        self.stream_game = None
        self._auto_started = False
        self._opened_seen = -1               # 用來發現「開過」名單有變動，更新清單上的記號
        self._checking = False               # 「檢查並修復」進行中
        self._library_loading = True         # 遊戲清單下載／讀取中
        self._library_loaded_at = time.time()  # 上次開始載入遊戲清單的時間
        self._new_games_dialog_open = False
        self._auto_stop_job = None           # 自動停止設定「等一下再套用」的計時器
        self._language_updaters = []         # 切換語言時要重新設定文字的元件
        self.idler = Idler(self.state, self.log)

        self._init_vars()
        self._build_ui()
        self._bind_traces()
        self.apply_language()
        self.root.report_callback_exception = self._report_error
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        if self.var_boot.get():
            try:
                set_autostart(True)          # 資料夾搬過的話，更新開機啟動的路徑
            except Exception:
                pass

        self.log(t("started_app", app=t("app_name"), version=VERSION, folder=DATA_DIR))
        threading.Thread(target=self._setup_worker, daemon=True).start()
        threading.Thread(target=self._discord_worker, daemon=True).start()
        self.root.after(200, self._poll_events)
        self.root.after(1000, self._tick)
        self.root.after(LIST_CHECK_MS, self._auto_refresh_library)

    # ---------- 變數 ----------
    def _init_vars(self) -> None:
        s = self.state.settings
        self.var_hours_current = tk.IntVar(value=s["hours_current"])
        self.var_hours_parallel = tk.IntVar(value=s["hours_parallel"])
        self.var_games_current = tk.IntVar(value=s["games_current"])
        self.var_games_target = tk.IntVar(value=s["games_target"])
        self.var_games_buffer = tk.IntVar(value=s["games_buffer"])
        self.var_minutes = tk.IntVar(value=s["minutes_per_game"])
        self.var_variety_parallel = tk.IntVar(value=s["variety_parallel"])
        self.var_then_hours = tk.BooleanVar(value=s["then_hours"])
        self.var_minimized = tk.BooleanVar(value=s["minimized"])
        self.var_auto_start = tk.BooleanVar(value=s["auto_start"])
        self.var_auto_stop = tk.BooleanVar(value=s["auto_stop"])
        self.var_auto_stop_hours = tk.DoubleVar(value=s["auto_stop_hours"])
        self.var_boot = tk.BooleanVar(value=get_autostart())
        self.var_stream_current = tk.IntVar(value=s["stream_current"])

    def _bind_traces(self) -> None:
        for var in (self.var_hours_current, self.var_games_current, self.var_games_target,
                    self.var_games_buffer, self.var_minutes, self.var_variety_parallel,
                    self.var_stream_current):
            var.trace_add("write", lambda *args: self._refresh_calcs())
        self.var_auto_stop_hours.trace_add("write", self._apply_auto_stop)    # 打字、按箭頭、滾輪都算

    @staticmethod
    def _int(var, default: int, low: int, high: int) -> int:
        """安全地讀取數字輸入框（打錯字就用預設值）。"""
        try:
            value = int(var.get())
        except (tk.TclError, ValueError, TypeError):
            return default
        return max(low, min(high, value))

    def _read_auto_stop_hours(self):
        """自動停止輸入框裡的小時數（可以有小數）；打錯字、太小或太大就回傳 None。"""
        try:
            value = float(self.var_auto_stop_hours.get())
        except (tk.TclError, ValueError, TypeError):
            return None
        low, high = AUTO_STOP_LIMITS
        return value if math.isfinite(value) and low <= value <= high else None

    def _auto_stop_seconds(self):
        """有勾「掛滿幾小時後自動停止」就回傳秒數，沒勾回傳 None。輸入框打錯就用上次有效的值。"""
        if not self.var_auto_stop.get():
            return None
        hours = self._read_auto_stop_hours()
        if hours is None:
            hours = self.state.settings["auto_stop_hours"]
        return hours * 3600

    # ---------- 語言 ----------
    def translate(self, widget, key: str):
        """設定元件上的文字，之後切換語言時會自動換成另一種語言。"""
        def update():
            widget.configure(text=t(key))
        update()
        self._language_updaters.append(update)
        return widget

    def _add_tab(self, notebook, tab, key: str) -> None:
        notebook.add(tab, text=t(key))
        self._language_updaters.append(lambda: notebook.tab(tab, text=t(key)))

    def apply_language(self) -> None:
        """把整個畫面換成目前的語言。"""
        self.root.title(f"{t('app_name')} v{VERSION}")
        for update in self._language_updaters:
            update()
        self._render_top_labels()
        self._render_help()
        self.picker_hours.update_texts()
        self.picker_stream.update_texts()
        self._refresh_calcs()
        self._refresh_status()

    def _on_language_selected(self, event=None) -> None:
        index = self.cmb_language.current()
        choice = LANGUAGE_CHOICES[index] if 0 <= index < len(LANGUAGE_CHOICES) else "auto"
        self.state.settings["language"] = choice
        self.state.save()
        set_language(resolve_language(choice))
        self.apply_language()
        self.log(t("language_changed"))

    # ---------- 介面 ----------
    def _setup_fonts(self) -> None:
        families = set(tkfont.families(self.root))
        family = next((f for f in ("Microsoft JhengHei UI", "Microsoft JhengHei", "Segoe UI") if f in families), None)
        for name in ("TkDefaultFont", "TkTextFont", "TkMenuFont", "TkHeadingFont"):
            try:
                font = tkfont.nametofont(name)
                if family:
                    font.configure(family=family, size=10)
            except tk.TclError:
                pass
        self.font_normal = tkfont.nametofont("TkDefaultFont")
        self.font_bold = self.font_normal.copy()
        self.font_bold.configure(weight="bold")

    def _build_ui(self) -> None:
        root = self.root
        try:      # 螢幕縮放 125%、150% 時，視窗跟著放大，並且不要超出螢幕
            factor = max(1.0, float(root.tk.call("tk", "scaling")) / (96 / 72))
            width = min(int(860 * factor), root.winfo_screenwidth() - 40)
            height = min(int(760 * factor), root.winfo_screenheight() - 80)
        except (tk.TclError, ValueError, TypeError):
            factor, width, height = 1.0, 860, 760
        self.wrap = int(780 * factor)            # 說明文字的換行寬度
        root.geometry(f"{width}x{height}")
        root.minsize(min(760, width), min(620, height))
        self._setup_fonts()

        top = ttk.Frame(root, padding=(12, 10, 12, 0))
        top.pack(fill="x")
        discord_box = ttk.Frame(top)
        discord_box.grid(row=0, column=0, sticky="w")
        self.lbl_discord = ttk.Label(discord_box)
        self.lbl_discord.pack(side="left")
        self.btn_discord = self.translate(ttk.Button(discord_box, command=self.open_discord), "open_discord")
        self.btn_discord.pack(side="left", padx=(8, 0))
        self.lbl_runner = ttk.Label(top)
        self.lbl_runner.grid(row=0, column=1, sticky="w", padx=(24, 0))
        language_box = ttk.Frame(top)
        language_box.grid(row=0, column=2, sticky="e")
        ttk.Label(language_box, text="語言 / Language:").pack(side="left", padx=(0, 4))
        self.cmb_language = ttk.Combobox(language_box, state="readonly", width=12, values=LANGUAGE_LABELS)
        self.cmb_language.current(LANGUAGE_CHOICES.index(self.state.settings["language"]))
        self.cmb_language.bind("<<ComboboxSelected>>", self._on_language_selected)
        self.cmb_language.pack(side="left")
        self.lbl_library = ttk.Label(top)
        self.lbl_library.grid(row=1, column=0, columnspan=2, sticky="w", pady=(4, 0))
        self.btn_reload = self.translate(ttk.Button(top, command=self.reload_library, state="disabled"),
                                         "reload_list")
        self.btn_reload.grid(row=1, column=2, sticky="e", pady=(4, 0))
        top.columnconfigure(1, weight=1)

        bar = ttk.Frame(root, padding=(12, 8, 12, 0))
        bar.pack(fill="x")
        self.lbl_status = ttk.Label(bar, font=self.font_bold)
        self.lbl_status.pack(side="left")
        self.translate(ttk.Button(bar, command=self.stop_all), "stop_all").pack(side="right")
        self.lbl_total = ttk.Label(root, text="", foreground=GRAY, padding=(12, 2, 12, 0))
        self.lbl_total.pack(fill="x")

        notebook = ttk.Notebook(root)
        notebook.pack(fill="both", expand=True, padx=12, pady=8)
        self.notebook = notebook
        self._build_hours_tab(notebook)
        self._build_variety_tab(notebook)
        self._build_stream_tab(notebook)
        self._build_help_tab(notebook)

        log_frame = self.translate(ttk.LabelFrame(root, padding=(6, 4)), "log_title")
        log_frame.pack(fill="x", padx=12, pady=(0, 12))
        self.txt_log = tk.Text(log_frame, height=6, wrap="word", state="disabled", font=self.font_normal)
        scroll = ttk.Scrollbar(log_frame, orient="vertical", command=self.txt_log.yview)
        self.txt_log.configure(yscrollcommand=scroll.set)
        self.txt_log.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

    def _build_hours_tab(self, notebook) -> None:
        tab = ttk.Frame(notebook, padding=10)
        self.tab_hours = tab
        self._add_tab(notebook, tab, "tab_hours")
        self.translate(ttk.Label(tab, justify="left", wraplength=self.wrap), "hours_intro").pack(anchor="w")

        self.picker_hours = GamePicker(tab, self, height=6, mode_key="hours_pick")
        self.picker_hours.pack(fill="both", expand=True, pady=(8, 6))

        row = ttk.Frame(tab)
        row.pack(fill="x")
        self.translate(ttk.Label(row), "parallel_label").pack(side="left")
        ttk.Spinbox(row, from_=1, to=MAX_PARALLEL, width=4, textvariable=self.var_hours_parallel).pack(side="left")
        self.translate(ttk.Label(row), "games_unit").pack(side="left", padx=(4, 20))
        self.translate(ttk.Checkbutton(row, variable=self.var_minimized), "minimize_windows").pack(side="left")

        row = ttk.Frame(tab)
        row.pack(fill="x", pady=(6, 0))
        self.translate(ttk.Label(row), "hours_current_label").pack(side="left")
        ttk.Spinbox(row, from_=0, to=1000000, width=8, textvariable=self.var_hours_current).pack(side="left")
        self.lbl_hours_calc = ttk.Label(row, text="")
        self.lbl_hours_calc.pack(side="left", padx=(8, 0))

        row = ttk.Frame(tab)
        row.pack(fill="x", pady=(6, 0))
        self.translate(ttk.Checkbutton(row, variable=self.var_auto_stop, command=self._apply_auto_stop),
                       "auto_stop_label").pack(side="left")
        low, high = AUTO_STOP_LIMITS
        spin = ttk.Spinbox(row, from_=low, to=high, increment=0.5, width=7, textvariable=self.var_auto_stop_hours)
        spin.pack(side="left", padx=(4, 0))
        spin.bind("<FocusOut>", self._tidy_auto_stop_text)    # 數字改了會自動套用（見 _bind_traces）
        self.translate(ttk.Label(row), "auto_stop_unit").pack(side="left", padx=(4, 0))

        row = ttk.Frame(tab)
        row.pack(fill="x", pady=(6, 0))
        self.translate(ttk.Checkbutton(row, variable=self.var_boot, command=self.toggle_boot),
                       "boot_start").pack(side="left")
        self.translate(ttk.Checkbutton(row, variable=self.var_auto_start, command=self._save_settings),
                       "auto_start").pack(side="left", padx=(20, 0))

        row = ttk.Frame(tab)
        row.pack(fill="x", pady=(10, 0))
        self.btn_hours = ttk.Button(row, command=self.toggle_hours)
        self.btn_hours.pack(side="left")
        self.btn_swap = self.translate(ttk.Button(row, command=self.swap_hours_game, state="disabled"), "swap_game")
        self.btn_swap.pack(side="left", padx=(8, 0))
        self.lbl_hours_info = ttk.Label(tab, text="", wraplength=self.wrap, justify="left")
        self.lbl_hours_info.pack(anchor="w", pady=(6, 0))

    def _build_variety_tab(self, notebook) -> None:
        tab = ttk.Frame(notebook, padding=10)
        self._add_tab(notebook, tab, "tab_variety")
        self.translate(ttk.Label(tab, justify="left", wraplength=self.wrap), "variety_intro").pack(anchor="w")

        grid = ttk.Frame(tab)
        grid.pack(fill="x", pady=(10, 0))
        fields = [
            ("games_current_label", self.var_games_current, 0, 100000),
            ("games_target_label", self.var_games_target, 1, 100000),
            ("games_buffer_label", self.var_games_buffer, 0, 100),
            ("minutes_label", self.var_minutes, 1, 240),
            ("variety_parallel_label", self.var_variety_parallel, 1, MAX_PARALLEL),
        ]
        for index, (key, var, low, high) in enumerate(fields):
            self.translate(ttk.Label(grid), key).grid(row=index, column=0, sticky="w", pady=2)
            ttk.Spinbox(grid, from_=low, to=high, width=8, textvariable=var).grid(row=index, column=1, sticky="w", pady=2)

        self.lbl_variety_plan = ttk.Label(tab, text="", wraplength=self.wrap, justify="left")
        self.lbl_variety_plan.pack(anchor="w", pady=(8, 0))
        self.translate(ttk.Checkbutton(tab, variable=self.var_then_hours), "then_hours").pack(anchor="w", pady=(6, 0))

        row = ttk.Frame(tab)
        row.pack(fill="x", pady=(10, 0))
        self.btn_variety = ttk.Button(row, command=self.toggle_variety)
        self.btn_variety.pack(side="left")
        self.translate(ttk.Button(row, command=self.clear_played), "clear_played").pack(side="left", padx=(8, 0))

        self.progress = ttk.Progressbar(tab, mode="determinate", maximum=1)
        self.progress.pack(fill="x", pady=(10, 0))
        self.lbl_variety_info = ttk.Label(tab, text="", wraplength=self.wrap, justify="left")
        self.lbl_variety_info.pack(anchor="w", pady=(6, 0))
        self.lbl_played = ttk.Label(tab, text="", foreground=GRAY)
        self.lbl_played.pack(anchor="w", pady=(4, 0))

    def _build_stream_tab(self, notebook) -> None:
        tab = ttk.Frame(notebook, padding=10)
        self._add_tab(notebook, tab, "tab_stream")
        self.translate(ttk.Label(tab, justify="left", wraplength=self.wrap), "stream_intro").pack(anchor="w")

        self.picker_stream = GamePicker(tab, self, height=6, mode_key="stream_pick")
        self.picker_stream.pack(fill="both", expand=True, pady=(8, 6))

        row = ttk.Frame(tab)
        row.pack(fill="x")
        self.translate(ttk.Label(row), "stream_current_label").pack(side="left")
        ttk.Spinbox(row, from_=0, to=1000000, width=8, textvariable=self.var_stream_current).pack(side="left")
        self.lbl_stream_calc = ttk.Label(row, text="")
        self.lbl_stream_calc.pack(side="left", padx=(8, 0))

        row = ttk.Frame(tab)
        row.pack(fill="x", pady=(10, 0))
        self.btn_stream_open = self.translate(ttk.Button(row, command=self.open_stream), "open_stream")
        self.btn_stream_open.pack(side="left")
        self.btn_stream_close = self.translate(ttk.Button(row, command=self.close_stream, state="disabled"),
                                               "close_stream")
        self.btn_stream_close.pack(side="left", padx=(8, 0))
        self.lbl_stream_info = ttk.Label(tab, text="")
        self.lbl_stream_info.pack(anchor="w", pady=(6, 0))

    def _build_help_tab(self, notebook) -> None:
        tab = ttk.Frame(notebook, padding=10)
        self._add_tab(notebook, tab, "tab_help")
        row = ttk.Frame(tab)
        row.pack(side="bottom", fill="x", pady=(8, 0))
        self.btn_check = self.translate(ttk.Button(row, command=self.run_self_check), "check_fix")
        self.btn_check.pack(side="left", padx=(0, 8))
        self.translate(ttk.Button(row, command=self.open_data_dir), "open_folder").pack(side="left")
        self.translate(ttk.Button(row, command=self.clear_bad), "clear_bad").pack(side="left", padx=(8, 0))
        self.translate(ttk.Button(row, command=self.delete_fake_files), "delete_files").pack(side="left", padx=(8, 0))

        self.txt_help = tk.Text(tab, wrap="word", font=self.font_normal, height=12, state="disabled")
        scroll = ttk.Scrollbar(tab, orient="vertical", command=self.txt_help.yview)
        self.txt_help.configure(yscrollcommand=scroll.set)
        self.txt_help.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

    def _render_help(self) -> None:
        self.txt_help.configure(state="normal")
        self.txt_help.delete("1.0", "end")
        self.txt_help.insert("1.0", t("help_text", data_dir=DATA_DIR, days=NEW_GAME_DAYS))
        self.txt_help.configure(state="disabled")

    def _render_top_labels(self) -> None:
        """上方三個狀態（Discord、執行器、遊戲清單）。"""
        if self.discord_running is True:
            text, color = t("discord_running"), GREEN
        elif self.discord_running is False:
            text, color = t("discord_not_running"), RED
        elif self.discord_checked:
            text, color = t("discord_unknown"), GRAY
        else:
            text, color = t("discord_checking"), ""
        self.lbl_discord.configure(text=text, foreground=color)
        self.btn_discord.configure(state="disabled" if self.discord_running is True else "normal")

        if self.runner is not None:
            text, color = t("runner_ready"), GREEN
        elif self.runner_error:
            text, color = t("runner_failed_short"), RED
        else:
            text, color = t("runner_preparing"), ""
        self.lbl_runner.configure(text=text, foreground=color)

        if self.library is not None:
            text, color = t("library_loaded", total=self.library.total_apps, usable=len(self.library.games)), ""
        elif self.library_error:
            text, color = t("library_failed_short"), RED
        else:
            text, color = t("library_loading"), ""
        self.lbl_library.configure(text=text, foreground=color)

    # ---------- 紀錄 ----------
    def log(self, message: str) -> None:
        if threading.current_thread() is not threading.main_thread():
            self.events.put(("log", message))      # 背景執行緒不能直接動介面
            return
        line = f"[{time.strftime('%H:%M:%S')}] {message}"
        write_log_file(line)
        self.txt_log.configure(state="normal")
        self.txt_log.insert("end", line + "\n")
        lines = int(self.txt_log.index("end-1c").split(".")[0])
        if lines > 500:
            self.txt_log.delete("1.0", f"{lines - 500}.0")
        self.txt_log.see("end")
        self.txt_log.configure(state="disabled")

    def _report_error(self, exc_type, exc_value, exc_tb) -> None:
        details = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        write_log_file("[ERROR] " + details)
        try:
            self.log(t("error_occurred", error=exc_value))
        except Exception:
            pass
        messagebox.showerror(t("app_name"), t("error_dialog", error=exc_value, path=LOG_FILE))

    # ---------- 背景工作 ----------
    def _setup_worker(self, force_download: bool = False, build: bool = True, quiet: bool = False) -> None:
        """quiet=True：背景自動更新清單，失敗時只寫紀錄、不跳錯誤視窗。"""
        post = self.events.put
        if build:
            try:
                post(("runner_ok", build_runner(log=lambda m: post(("log", m)))))
            except Exception as exc:
                post(("runner_error", (str(exc), isinstance(exc, CscMissingError))))
        try:
            self._load_library_job(force_download, post)
        except Exception as exc:
            post(("library_error", (str(exc), quiet)))

    @staticmethod
    def _load_library_job(force_download: bool, post):
        """（背景執行緒）載入遊戲清單，再跟之前看過的比對，找出 Discord 新增的遊戲。"""
        library = load_library(force_download, log=lambda m: post(("log", m)))
        post(("library_ok", library))
        try:
            new_games = find_new_games(library)
        except Exception:
            write_log_file("[ERROR] " + traceback.format_exc())
            new_games = []
        if new_games:
            post(("new_games", new_games))
        return library

    def _start_library_load(self, force_download: bool, quiet: bool = False) -> None:
        self._library_loading = True
        self._library_loaded_at = time.time()
        self.btn_reload.configure(state="disabled")
        threading.Thread(target=self._setup_worker, daemon=True,
                         kwargs={"force_download": force_download, "build": False, "quiet": quiet}).start()

    def _auto_refresh_library(self) -> None:
        """程式一直開著掛機時，遊戲清單每天自動更新一次（才會發現 Discord 新增的遊戲）。"""
        try:
            before = len(self.state.new_games)
            self.state.prune_new_games()
            if len(self.state.new_games) != before and self.library is not None:   # 有遊戲過了期限，拿掉 ★
                for picker in (self.picker_hours, self.picker_stream):
                    if picker.mode() == "new" and not self.state.new_games:
                        picker.set_mode("all", clear_search=False)   # 一款新遊戲都不剩了，清單才不會變空的
                    else:
                        picker.refresh_keep()
            try:
                age = time.time() - CACHE_FILE.stat().st_mtime     # 清單多久沒成功下載了
            except OSError:
                age = float("inf")
            since_try = time.time() - self._library_loaded_at
            retry = 3600 if self.library is None else LIST_RETRY_SECONDS
            if age >= LIST_MAX_AGE and since_try >= retry and not self._library_loading:
                self.log(t("list_auto_refresh"))
                self._start_library_load(force_download=False, quiet=True)
        finally:
            self.root.after(LIST_CHECK_MS, self._auto_refresh_library)

    def _discord_worker(self) -> None:
        while True:
            self.events.put(("discord", is_discord_running()))
            time.sleep(15)

    def _poll_events(self) -> None:
        try:
            while True:
                try:
                    kind, payload = self.events.get_nowait()
                except queue.Empty:
                    break
                try:
                    self._handle_event(kind, payload)
                except Exception as exc:
                    write_log_file("[ERROR] " + traceback.format_exc())
                    self.log(t("event_error", error=exc))
        finally:
            self.root.after(200, self._poll_events)

    def _handle_event(self, kind: str, payload) -> None:
        if kind == "log":
            self.log(payload)
        elif kind == "runner_ok":
            self.runner = payload
            self.idler.runner = payload
            self.runner_error = None
            self._render_top_labels()
            self._maybe_autostart()
        elif kind == "runner_error":
            message, csc_missing = payload
            self.runner_error = message
            self._render_top_labels()
            self.log(t("runner_failed_log", error=message))
            messagebox.showerror(t("app_name"), t("runner_failed", error=message))
            if csc_missing and messagebox.askyesno(t("app_name"), t("ask_open_dotnet")):
                webbrowser.open(DOTNET_DOWNLOAD_URL)
        elif kind == "library_ok":
            first = self.library is None
            self.library = payload
            self.library_error = None
            self.idler.library = payload
            self._library_loading = False
            self.btn_reload.configure(state="normal")
            self._render_top_labels()
            if first:
                self.picker_hours.refresh()
                self.picker_stream.refresh()
                saved = payload.by_id.get(self.state.settings.get("hours_game_id", ""))
                if saved is not None:
                    self.picker_hours.select_game(saved)
            else:                                   # 重新下載清單：保留目前選的遊戲
                self.picker_hours.refresh_keep()
                self.picker_stream.refresh_keep()
            self.log(t("library_ready_log", count=len(payload.games)))
            self._maybe_autostart()
        elif kind == "library_error":
            message, quiet = payload
            self._library_loading = False
            self.btn_reload.configure(state="normal")
            self.library_error = message
            self._render_top_labels()
            self.log(t("library_failed_log", error=message))
            if not quiet:
                messagebox.showerror(t("app_name"), message)
        elif kind == "new_games":
            self._on_new_games(payload)
        elif kind == "discord":
            self.discord_running = payload
            self.discord_checked = True
            self.idler.discord_running = payload is not False
            self._render_top_labels()
        elif kind == "selfcheck_done":
            self._show_self_check(*payload)

    def _maybe_autostart(self) -> None:
        if self._auto_started or self.runner is None or self.library is None:
            return
        self._auto_started = True
        if self.var_auto_start.get() and self.idler.mode is None:
            self.log(t("auto_starting"))
            if self.discord_running is False and find_discord() is not None:
                self.open_discord()
            self.start_hours(confirm=False)

    def reload_library(self) -> None:
        self._start_library_load(force_download=True)

    # ---------- 新遊戲 ----------
    def _on_new_games(self, games) -> None:
        """Discord 新增了遊戲：記下來、在清單上標記、寫紀錄，並跳出通知。"""
        games = [game for game in games if game.id not in self.state.new_games]    # 已經通知過的不再通知
        if not games:
            return
        self.state.add_new_games(games)
        self.state.save()
        self.picker_hours.refresh_keep()
        self.picker_stream.refresh_keep()
        names = [game.name for game in games]
        short = t("sep").join(names[:10]) + (t("and_more", count=len(names) - 10) if len(names) > 10 else "")
        self.log(t("new_games_log", count=len(names), names=short))
        # 通知視窗用 after 另外開：視窗開著沒人按的時候，其他事件（Discord 狀態等）還是會繼續處理
        self.root.after(0, self._ask_show_new_games, names)

    def _ask_show_new_games(self, names) -> None:
        if self._new_games_dialog_open:             # 上一個通知還沒關，就不要再疊一個
            return
        listed = "\n".join("• " + name for name in names[:15])
        if len(names) > 15:
            listed += "\n" + t("and_more", count=len(names) - 15)
        self._new_games_dialog_open = True
        try:
            show = messagebox.askyesno(t("app_name"), t("new_games_dialog", count=len(names), names=listed,
                                                        days=NEW_GAME_DAYS))
        finally:
            self._new_games_dialog_open = False
        if show:
            self.show_new_games()

    def show_new_games(self) -> None:
        """切到「遊戲時數」分頁，清單只顯示新遊戲。"""
        self.notebook.select(self.tab_hours)
        self.picker_hours.set_mode("new")

    # ---------- 每秒更新 ----------
    def _tick(self) -> None:
        try:
            self.idler.tick()
            if self.stream_game is not None and self.stream_game.exit_code() is not None:
                self.stream_game.stop()
                self.stream_game = None
                self.log(t("stream_window_closed"))
            if self.library is not None and len(self.state.opened_ids) != self._opened_seen:
                self._opened_seen = len(self.state.opened_ids)
                self.picker_hours.refresh_keep()
                self.picker_stream.refresh_keep()
            self._refresh_status()
        except Exception as exc:
            write_log_file("[ERROR] " + traceback.format_exc())
            self.log(t("internal_error", error=exc))
        finally:
            self.root.after(1000, self._tick)

    def _refresh_calcs(self) -> None:
        hours = self._int(self.var_hours_current, 0, 0, 10 ** 6)
        tier = next_tier(hours, HOURS_TIERS)
        if tier:
            left = tier[1] - hours
            self.lbl_hours_calc.configure(text=t("hours_calc", tier=tier[0], need=tier[1], left=left,
                                                 days=left / 24))
        else:
            self.lbl_hours_calc.configure(text=t("hours_max"))

        current = self._int(self.var_games_current, 0, 0, 10 ** 6)
        target = self._int(self.var_games_target, 100, 1, 10 ** 6)
        buffer = self._int(self.var_games_buffer, 0, 0, 1000)
        minutes = self._int(self.var_minutes, 15, 1, 240)
        parallel = self._int(self.var_variety_parallel, 1, 1, MAX_PARALLEL)
        need = max(0, target - current)
        upcoming = [t("tier_games", tier=name, count=count) for name, count in GAMES_TIERS if count > current][:2]
        upcoming_text = t("sep").join(upcoming) if upcoming else t("games_max")
        if need:
            total = need + buffer
            seconds = math.ceil(total / parallel) * minutes * 60
            plan = t("variety_plan", total=total, need=need, buffer=buffer,
                     duration=fmt_hours_minutes(seconds), tiers=upcoming_text)
        else:
            plan = t("variety_plan_done", tiers=upcoming_text)
        self.lbl_variety_plan.configure(text=plan)

        streamed = self._int(self.var_stream_current, 0, 0, 10 ** 6)
        tier = next_tier(streamed, STREAM_TIERS)
        if tier:
            self.lbl_stream_calc.configure(text=t("stream_calc", tier=tier[0], need=tier[1], left=tier[1] - streamed))
        else:
            self.lbl_stream_calc.configure(text=t("stream_max"))

    def _refresh_status(self) -> None:
        idler = self.idler
        session = fmt_duration(idler.session_seconds)
        if idler.mode == "hours":
            text = t("status_hours", count=len(idler.slots), time=session)
            if idler.stop_after is not None:
                text += t("status_auto_stop", time=fmt_hours_minutes(idler.stop_after - idler.session_seconds))
        elif idler.mode == "variety":
            text = t("status_variety", done=idler.variety_done, total=idler.variety_total, time=session)
        else:
            text = t("status_idle")
        if idler.mode is not None and not idler.discord_running:
            text += t("status_paused")
        if self.stream_game is not None:
            text += t("status_streaming")
        self.lbl_status.configure(text=text)
        self.lbl_total.configure(text=t("total_idle", hours=self.state.total_seconds / 3600))

        # 時數分頁
        if idler.mode == "hours":
            names = t("sep").join(fake.game.name for fake in idler.slots)
            self.lbl_hours_info.configure(text=t("running_list", names=names))
            self.btn_hours.configure(text=t("stop_hours"))
            self.btn_swap.configure(state="normal")
        else:
            stopped = t("auto_stopped", time=fmt_hours_minutes(idler.auto_stopped)) if idler.auto_stopped else ""
            self.lbl_hours_info.configure(text=stopped)
            self.btn_hours.configure(text=t("start_hours"))
            self.btn_swap.configure(state="disabled")

        # 款數分頁
        if idler.mode == "variety":
            parts = [t("variety_part", name=fake.game.name,
                       time=fmt_duration(idler.variety_seconds - fake.play_seconds)) for fake in idler.slots]
            self.progress.configure(maximum=max(1, idler.variety_total),
                                    value=idler.variety_done + idler.variety_skipped)
            self.lbl_variety_info.configure(text=t(
                "variety_info", parts=t("sep").join(parts) or "—", done=idler.variety_done,
                skipped=idler.variety_skipped, queued=len(idler.queue),
                eta=fmt_hours_minutes(idler.variety_eta_seconds())))
            self.btn_variety.configure(text=t("stop_variety"))
        else:
            if idler.last_result is not None:
                done, skipped = idler.last_result
                self.lbl_variety_info.configure(text=t("last_summary", done=done, skipped=skipped))
            else:
                self.lbl_variety_info.configure(text="")
            self.btn_variety.configure(text=t("start_variety"))
        self.lbl_played.configure(text=t("played_count", count=len(self.state.opened_ids)))

        # 直播分頁
        if self.stream_game is not None:
            self.btn_stream_open.configure(state="disabled")
            self.btn_stream_close.configure(state="normal")
            self.lbl_stream_info.configure(text=t("stream_open_info", name=self.stream_game.game.name))
        else:
            self.btn_stream_open.configure(state="normal")
            self.btn_stream_close.configure(state="disabled")
            self.lbl_stream_info.configure(text=t("stream_closed_info"))

    # ---------- 按鈕 ----------
    def _check_ready(self) -> bool:
        if self.runner is None:
            if self.runner_error:
                messagebox.showerror(t("app_name"), t("runner_failed", error=self.runner_error))
            else:
                messagebox.showinfo(t("app_name"), t("runner_not_ready"))
            return False
        if self.library is None:
            messagebox.showinfo(t("app_name"), t("library_not_ready"))
            return False
        return True

    def _confirm_discord(self) -> bool:
        """Discord 沒開的話：有安裝就問要不要幫忙開，沒安裝就確認要不要照樣開始。"""
        if self.discord_running is not False:
            return True
        if find_discord() is None:
            return messagebox.askyesno(t("app_name"), t("confirm_no_discord"))
        answer = messagebox.askyesnocancel(t("app_name"), t("ask_launch_discord"))
        if answer is None:
            return False
        if answer:
            self.open_discord()
        return True

    def open_discord(self) -> None:
        try:
            launched = launch_discord()
        except OSError as exc:
            messagebox.showerror(t("app_name"), t("discord_launch_failed", error=exc))
            return
        if launched:
            self.log(t("discord_launching"))
            threading.Thread(target=self._wait_for_discord, daemon=True).start()
        elif messagebox.askyesno(t("app_name"), t("discord_not_installed")):
            webbrowser.open(DISCORD_DOWNLOAD_URL)

    def _wait_for_discord(self) -> None:
        """剛開 Discord 時，每 5 秒檢查一次，最多 30 秒，讓狀態早點更新。"""
        for _ in range(6):
            time.sleep(5)
            running = is_discord_running()
            self.events.put(("discord", running))
            if running:
                return

    # ---------- 檢查並修復 ----------
    def run_self_check(self) -> None:
        if self._checking:
            return
        self._checking = True
        self.btn_check.configure(state="disabled")
        self.log(t("checking"))
        threading.Thread(target=self._self_check_worker, args=(self.library,), daemon=True).start()

    def _self_check_worker(self, library) -> None:
        post = self.events.put
        results = []          # (記號, 說明)
        actions = []          # 檢查完要問你的事
        detail = t("chk_app_exe") if IS_FROZEN else t("chk_app_py", version=platform.python_version())
        results.append(("✓", t("chk_app", detail=detail)))

        try:                                                   # 1) 資料夾能不能寫
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            probe = DATA_DIR / "write_test.tmp"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink()
            results.append(("✓", t("chk_folder_ok")))
        except OSError as exc:
            results.append(("✗", t("chk_folder_fail", error=exc)))

        missing = not (RUNNER_DIR / "BadgeIdlerRunner.exe").is_file()
        try:                                                   # 2) 假遊戲執行器：不見就重建，再試跑
            runner = build_runner(log=lambda m: post(("log", m)))
            post(("runner_ok", runner))
            results.append(("✓", t("chk_runner_fixed") if missing else t("chk_runner_ok")))
            error = self_test_launch(runner)
            results.append(("✓", t("chk_launch_ok")) if error is None else ("✗", t("chk_launch_fail", error=error)))
        except Exception as exc:
            results.append(("✗", t("chk_runner_fail", error=exc)))
            if isinstance(exc, CscMissingError):
                actions.append("dotnet")

        if library is None:                                    # 3) 遊戲清單：沒載入就重新下載
            try:
                library = self._load_library_job(True, post)
                results.append(("✓", t("chk_list_fixed", count=len(library.games))))
            except Exception as exc:
                results.append(("✗", t("chk_list_fail", error=exc)))
        else:
            results.append(("✓", t("chk_list_ok", count=len(library.games))))

        running = is_discord_running()                         # 4) Discord
        post(("discord", running))
        if running is True:
            results.append(("✓", t("chk_discord_running")))
        elif find_discord() is None:
            results.append(("✗", t("chk_discord_missing")))
            actions.append("discord_download")
        elif running is False:
            results.append(("!", t("chk_discord_closed")))
            actions.append("discord_launch")
        else:
            results.append(("!", t("chk_discord_unknown")))
        post(("selfcheck_done", (results, actions)))

    def _show_self_check(self, results, actions) -> None:
        self._checking = False
        self.btn_check.configure(state="normal")
        lines = [f"{mark} {text}" for mark, text in results]
        for line in lines:
            self.log(line)
        if all(mark == "✓" for mark, _ in results):
            lines += ["", t("check_all_ok")]
        messagebox.showinfo(t("check_title"), "\n".join(lines))
        if "dotnet" in actions and messagebox.askyesno(t("app_name"), t("ask_open_dotnet")):
            webbrowser.open(DOTNET_DOWNLOAD_URL)
        if "discord_launch" in actions and messagebox.askyesno(t("app_name"), t("ask_open_discord_now")):
            self.open_discord()
        if "discord_download" in actions and messagebox.askyesno(t("app_name"), t("discord_not_installed")):
            webbrowser.open(DISCORD_DOWNLOAD_URL)

    def toggle_hours(self) -> None:
        if self.idler.mode == "hours":
            self.idler.stop()
        else:
            self.start_hours()
        self._refresh_status()

    def start_hours(self, confirm: bool = True) -> None:
        if not self._check_ready():
            return
        if confirm:
            if self.idler.mode == "variety" and not messagebox.askyesno(t("app_name"), t("confirm_stop_variety")):
                return
            if not self._confirm_discord():
                return
        game = self.picker_hours.selected()
        parallel = self._int(self.var_hours_parallel, 1, 1, MAX_PARALLEL)
        if self.idler.start_hours(game, parallel, self.var_minimized.get(), self.picker_hours.mode(),
                                  self._auto_stop_seconds()):
            self._save_settings()
        self._refresh_status()

    def _apply_auto_stop(self, *args) -> None:
        """勾選或改了自動停止的時數：停 0.8 秒沒再改才套用（按住箭頭、打字到一半時不會一直套用）。"""
        if self._auto_stop_job is not None:
            self.root.after_cancel(self._auto_stop_job)
        self._auto_stop_job = self.root.after(800, self._apply_auto_stop_now)

    def _apply_auto_stop_now(self) -> None:
        """記住設定；正在掛時數的話，從現在開始倒數（設定沒變就不會重新倒數）。"""
        self._auto_stop_job = None
        self._save_settings()
        seconds = self._auto_stop_seconds()
        if self.idler.mode == "hours":
            self.idler.set_stop_after(seconds)
        elif self.idler.mode == "variety" and self.idler.then_hours is not None:
            self.idler.then_hours["stop_after"] = seconds          # 款數跑完接著掛時數時用
        self._refresh_status()

    def _tidy_auto_stop_text(self, event=None) -> None:
        """離開輸入框時，打錯字或超出範圍的數字改回目前有效的值。"""
        if self._read_auto_stop_hours() is None:
            self.var_auto_stop_hours.set(self.state.settings["auto_stop_hours"])

    def swap_hours_game(self) -> None:
        if self.idler.mode != "hours":
            messagebox.showinfo(t("app_name"), t("start_hours_first"))
            return
        fake = self.idler.replace_main()
        if fake is not None:
            self.picker_hours.select_game(fake.game)
            self._save_settings()
        self._refresh_status()

    def toggle_variety(self) -> None:
        if self.idler.mode == "variety":
            self.idler.stop()
        else:
            self.start_variety()
        self._refresh_status()

    def start_variety(self) -> None:
        if not self._check_ready():
            return
        current = self._int(self.var_games_current, 0, 0, 10 ** 6)
        target = self._int(self.var_games_target, 100, 1, 10 ** 6)
        buffer = self._int(self.var_games_buffer, 0, 0, 1000)
        minutes = self._int(self.var_minutes, 15, 1, 240)
        parallel = self._int(self.var_variety_parallel, 1, 1, MAX_PARALLEL)
        need = max(0, target - current)
        if need == 0:
            messagebox.showinfo(t("app_name"), t("target_reached"))
            return
        if self.idler.mode == "hours" and not messagebox.askyesno(t("app_name"), t("confirm_stop_hours")):
            return
        if not self._confirm_discord():
            return
        then = None
        if self.var_then_hours.get():
            then = {"game": self.picker_hours.selected(),
                    "parallel": self._int(self.var_hours_parallel, 1, 1, MAX_PARALLEL),
                    "minimized": self.var_minimized.get(),
                    "pick_mode": self.picker_hours.mode(),
                    "stop_after": self._auto_stop_seconds()}
        if self.idler.start_variety(need + buffer, minutes, parallel, self.var_minimized.get(), then):
            self._save_settings()
        self._refresh_status()

    def clear_played(self) -> None:
        count = len(self.state.opened_ids | self.state.played_ids)
        if count == 0:
            messagebox.showinfo(t("app_name"), t("no_played"))
            return
        if messagebox.askyesno(t("app_name"), t("confirm_clear_played", count=count)):
            self.state.played_ids.clear()
            self.state.opened_ids.clear()
            self.state.save()
            self.log(t("cleared_played"))
            self._refresh_status()

    def clear_bad(self) -> None:
        count = len(self.state.bad_ids)
        if count == 0:
            messagebox.showinfo(t("app_name"), t("bad_empty"))
            return
        if messagebox.askyesno(t("app_name"), t("confirm_clear_bad", count=count)):
            self.state.bad_ids.clear()
            self.state.save()
            self.log(t("cleared_bad"))

    def open_stream(self) -> None:
        if not self._check_ready():
            return
        if self.stream_game is not None:
            messagebox.showinfo(t("app_name"), t("stream_already_open"))
            return
        game = self.picker_stream.selected()
        if game is None:
            picks = self.idler.pick_games(1, self.picker_stream.mode())
            if not picks:
                messagebox.showinfo(t("app_name"), t("no_match"))
                return
            game = picks[0]
            self.picker_stream.select_game(game)
        fake = FakeGame(game, self.runner, stream=True)
        try:
            fake.start()
        except (OSError, ValueError, subprocess.SubprocessError) as exc:
            messagebox.showerror(t("app_name"), t("stream_open_failed", error=explain_launch_error(exc)))
            return
        self.stream_game = fake
        self.state.opened_ids.add(game.id)
        self.log(t("stream_opened", name=game.name))
        self._refresh_status()

    def close_stream(self) -> None:
        if self.stream_game is not None:
            self.stream_game.stop()
            self.stream_game = None
            self.log(t("stream_closed_log"))
        self._refresh_status()

    def stop_all(self) -> None:
        self.idler.stop()
        self.close_stream()

    def toggle_boot(self) -> None:
        want = self.var_boot.get()
        try:
            set_autostart(want)
            self.log(t("boot_on") if want else t("boot_off"))
        except Exception as exc:
            self.var_boot.set(not want)
            messagebox.showerror(t("app_name"), t("setting_failed", error=exc))
            return
        if want and not self.var_auto_start.get() and messagebox.askyesno(t("app_name"), t("suggest_auto_start")):
            self.var_auto_start.set(True)
            self._save_settings()

    def open_data_dir(self) -> None:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        if hasattr(os, "startfile"):
            os.startfile(str(DATA_DIR))

    def delete_fake_files(self) -> None:
        if self.idler.mode is not None or self.stream_game is not None:
            messagebox.showinfo(t("app_name"), t("stop_first"))
            return
        if messagebox.askyesno(t("app_name"), t("confirm_delete_files")):
            shutil.rmtree(GAMES_DIR, ignore_errors=True)
            self.log(t("deleted_files"))

    def _save_settings(self) -> None:
        s = self.state.settings
        s["hours_current"] = self._int(self.var_hours_current, s["hours_current"], 0, 10 ** 6)
        s["hours_parallel"] = self._int(self.var_hours_parallel, s["hours_parallel"], 1, MAX_PARALLEL)
        s["games_current"] = self._int(self.var_games_current, s["games_current"], 0, 10 ** 6)
        s["games_target"] = self._int(self.var_games_target, s["games_target"], 1, 10 ** 6)
        s["games_buffer"] = self._int(self.var_games_buffer, s["games_buffer"], 0, 1000)
        s["minutes_per_game"] = self._int(self.var_minutes, s["minutes_per_game"], 1, 240)
        s["variety_parallel"] = self._int(self.var_variety_parallel, s["variety_parallel"], 1, MAX_PARALLEL)
        s["stream_current"] = self._int(self.var_stream_current, s["stream_current"], 0, 10 ** 6)
        s["then_hours"] = bool(self.var_then_hours.get())
        s["minimized"] = bool(self.var_minimized.get())
        s["auto_start"] = bool(self.var_auto_start.get())
        s["auto_stop"] = bool(self.var_auto_stop.get())
        hours = self._read_auto_stop_hours()
        if hours is not None:
            s["auto_stop_hours"] = hours
        if self.idler.mode == "hours" and self.idler.slots:
            s["hours_game_id"] = self.idler.slots[0].game.id
        else:
            game = self.picker_hours.selected()
            if game is not None:
                s["hours_game_id"] = game.id
        self.state.save()

    def on_close(self) -> None:
        busy = self.idler.mode is not None or self.stream_game is not None
        if busy and not messagebox.askyesno(t("app_name"), t("confirm_close")):
            return
        self._save_settings()
        self.idler.stop(quiet=True)
        if self.stream_game is not None:
            self.stream_game.stop()
            self.stream_game = None
        self.root.destroy()


# ============================================================================
# 程式進入點
# ============================================================================

def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    saved = State(STATE_FILE)
    saved.load()
    set_language(resolve_language(saved.settings["language"]))     # 開視窗前的訊息也用你選的語言
    if tk is None:
        show_native_error(t("app_name"), t("need_tkinter"))
        return 1
    if os.name != "nt":
        show_native_error(t("app_name"), t("windows_only"))
        return 1
    enable_dpi_awareness()
    if not acquire_single_instance():
        root = tk.Tk()
        root.withdraw()
        messagebox.showinfo(t("app_name"), t("already_running"))
        root.destroy()
        return 0
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    rotate_log()
    root = tk.Tk()
    App(root, autostart="--autostart" in argv)
    if "--autostart" in argv:
        root.iconify()            # 開機自動啟動時先縮到工作列
    root.mainloop()
    return 0


def run() -> int:
    """程式入口：任何沒處理到的錯誤都會跳出錯誤視窗並存成 crash_log.txt，不會無聲無息地關掉。"""
    try:
        return main()
    except KeyboardInterrupt:
        return 130
    except SystemExit:
        raise
    except BaseException:
        details = traceback.format_exc()
        if sys.stderr is not None:
            sys.stderr.write(details)
        path = write_crash_log(details)
        last_line = details.strip().splitlines()[-1] if details.strip() else "?"
        show_native_error(t("app_name"), t("fatal_error", error=last_line, path=path))
        return 1


if __name__ == "__main__":
    sys.exit(run())
