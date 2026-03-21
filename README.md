# 🏆 Rudi Madness - Live Fantasy March Madness Tracker

A real-time, zero-touch fantasy college basketball dashboard built with Python and Streamlit. 

This application tracks custom fantasy league rosters, automatically pulls live box scores during the NCAA Tournament, and instantly crosses off teams as they are eliminated. It is designed to be hosted in the cloud and cast to a TV or tablet as a hands-free, auto-refreshing live leaderboard.

## ✨ Features

* **Real-Time Live Scoring:** Bypasses slow third-party wrappers and pings the public ESPN College Basketball API directly to pull live box scores, calculating total fantasy points (Points + Rebounds + Assists) by the minute.
* **Smart College Mapping:** Uses the `sportsdataverse` historical database to automatically look up and memorize which college every player attends (cached once every 24 hours to prevent slow load times).
* **Auto-Elimination Engine:** Constantly monitors the ESPN live scoreboard for completed games. If a player's team loses, they are instantly tagged with a ❌ and moved to the bottom of your active roster.
* **TV-Ready Auto-Refresh:** The web page automatically redraws itself every 60 seconds, meaning you never have to manually hit refresh during a busy slate of games.
* **Mobile-Friendly UI:** Features a custom CSS-styled, responsive leaderboard with row banding and collapsible manager rosters showing active survival counts.

## 📁 Prerequisites & Setup

### 1. The Roster File (`rosters.csv`)
The application relies on a local CSV file to know who is in your league and who they drafted. You must create a file named `rosters.csv` in the root directory.

The CSV must contain at least these two columns (spelling matters!):
* `Player`: The exact spelling of the player's name as it appears in the ESPN database (e.g., "R.J. Davis", not "RJ Davis").
* `Fantasy Owner` (or `Fantasy Team`): The name of the manager who drafted them.

**Example `rosters.csv`:**
| Player | Fantasy Owner |
| :--- | :--- |
| Hunter Dickinson | Jimmy Wilson |
| Caleb Love | Sprung Peters |
| Mark Sears | Dr. Jeffrey S. Pigott |

### 2. Dependencies (`requirements.txt`)
To run this application locally or deploy it to Streamlit Cloud, ensure your `requirements.txt` file includes the following packages. *(Note: Version limits on xgboost and setuptools are required to prevent sportsdataverse dependency crashes).*

```text
streamlit
pandas
requests
sportsdataverse
xgboost<3.0.0
setuptools<70.0.0