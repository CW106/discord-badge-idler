# 更新紀錄 / Changelog

每個版本都可以在 [Releases](../../releases) 下載。
Every version can be downloaded from [Releases](../../releases).

## v1.6

**介面全面改版**
- Discord 風格的深色介面：Discord 配色、藍紫色主要按鈕，掛機中按鈕會變成紅色「停止」
- 目前狀態、Discord、遊戲清單的狀況集中在上方的卡片
- 新的程式圖示（視窗、工作列和 EXE 都有），Windows 10／11 的標題列也變成深色
- 圓角勾選框；「說明」分頁的小標題改成粗體
- 視窗太矮或螢幕縮放比較大時，只會縮短遊戲清單，按鈕不會被擠掉

**Redesigned interface**
- Dark, Discord-style theme with Discord colors and blurple buttons; the start button turns into a red Stop button while idling
- Status, Discord, dummy game runner and game list info grouped in a card at the top
- New app icon (window, taskbar and EXE) and a dark title bar on Windows 10/11
- Rounded checkboxes and bold section headings on the Help tab
- When the window is short or display scaling is high, only the game list shrinks, so the buttons stay visible

## v1.5

**新遊戲通知**
- 遊戲清單每天自動更新，程式一直開著掛機也會更新
- Discord 新增遊戲時會跳出通知，列出是哪幾款；新遊戲在清單裡前面有 ★（14 天內）
- 遊戲清單的範圍多了「只看新遊戲」
- 第一次開這個版本時，會先記下現有的遊戲，之後新增的才會通知

**自動停止的改進**
- 掛到一半才勾選或修改時間，改成從那時候開始倒數（v1.4 如果已經掛超過設定的時間，一勾就會停）
- 打字打到一半不會套用，打錯的數字會改回原本的值

**New game notifications**
- The game list updates itself every day, even while the app keeps idling
- When Discord adds games, a pop-up lists them, and new games get a ★ in the list for 14 days
- New "New games" option in the Show menu
- The first run of this version records the current games; you're notified about games added after that

**Auto-stop improvements**
- Turning auto-stop on or changing it mid-session now starts the countdown from that moment (in v1.4 it could stop right away if you had already idled longer than the limit)
- Half-typed values aren't applied, and invalid numbers revert to the last valid one

## v1.4

**定時自動停止**
- 新增「掛滿 N 小時後自動停止」（遊戲時數分頁）：可以填小數，只算 Discord 開著的時間；時間到會停掉所有假遊戲，電腦也會恢復自動睡眠
- 跑完款數、自動接著掛時數時，也會照這個設定停止

**Auto-stop**
- New "Stop automatically after N hours of idling" option on the Game hours tab: decimals are allowed and only time with Discord open counts; when the time is up, all dummy games stop and Windows can sleep again
- Also applies when games-played mode switches to hours mode at the end

## v1.3

**EXE 版與檢查並修復**
- 第一個 EXE 版：不需要安裝 Python，下載就能用
- 新增「檢查並修復」：自動檢查並修好資料夾、假遊戲執行器（不見就重建，並試跑看有沒有被防毒擋下）、遊戲清單和 Discord
- 新增「開啟 Discord」按鈕；Discord 沒開時按開始，會問要不要幫你開
- 程式當掉時會跳出錯誤視窗，並把詳細內容存成 crash_log.txt
- start.bat 找不到 Python 時可以自動安裝，啟動時的錯誤會存成 last_error.txt
- 缺少 .NET Framework 時會提示下載

**EXE build and Check & repair**
- First EXE build: no Python needed
- New Check & repair button: checks and fixes the data folder, the dummy game runner (rebuilt if missing, plus a test launch that catches antivirus blocks), the game list and Discord
- New Open Discord button; starting while Discord is closed offers to open it
- Crashes show an error pop-up and save the details to crash_log.txt
- start.bat can install Python for you and saves startup errors to last_error.txt
- Points you to the .NET Framework download if the C# compiler is missing

## v1.2

**同時執行與遊戲範圍**
- 「同時執行」上限從 10 款提高到 100 款
- 遊戲清單可以選擇範圍：全部遊戲／只看開過的／只看沒開過的，隨機挑選也會照這個範圍

**Run at once and game filter**
- "Run at once" now goes up to 100 games (was 10)
- New Show menu in the game list: all games, opened before, or never opened; random picks follow it
