import streamlit as st
import pandas as pd
import requests
import os
import warnings

warnings.simplefilter(action='ignore', category=FutureWarning)

# --- 1. PAGE SETUP ---
st.set_page_config(page_title="Rudi Madness", page_icon="🏆", layout="wide")
st.title("🏆 Live Rudi Madness Tracker")
st.markdown("Stats and eliminations automatically refresh directly from the live ESPN scoreboard.")

# --- 2. LOAD ROSTERS FROM LOCAL CSV ---
@st.cache_data(ttl=300) 
def load_rosters():
    if not os.path.exists("rosters.csv"):
        st.error("⚠️ 'rosters.csv' not found! Please create it in your VSCode folder.")
        return {}
        
    try:
        roster_df = pd.read_csv("rosters.csv")
        owner_dict = {}
        for index, row in roster_df.iterrows():
            player = str(row['Player']).strip()
            owner = str(row['Fantasy Team']).strip()
            owner_dict[player] = owner
        return owner_dict
    except Exception as e:
        st.error(f"Failed to read 'rosters.csv': {e}")
        return {}

player_to_owner = load_rosters()

# --- 3. THE AUTO-ELIMINATION ENGINE (LIVE ESPN FEED) ---
@st.cache_data(ttl=120)
def get_eliminated_teams():
    eliminated = []
    # Dates for the First Four through the end of the first weekend
    tourney_dates = ['20260317', '20260318', '20260319', '20260320', '20260321', '20260322']
    
    for date_str in tourney_dates:
        url = f"https://site.api.espn.com/apis/site/v2/sports/basketball/mens-college-basketball/scoreboard?dates={date_str}"
        try:
            data = requests.get(url).json()
            for event in data.get('events', []):
                comp = event['competitions'][0]
                
                # Check if the game is completely finished
                if comp['status']['type']['completed']: 
                    for team in comp['competitors']:
                        # If the winner flag is False, they are eliminated
                        if team.get('winner') == False:
                            eliminated.append(team['team']['displayName'])
        except:
            pass
            
    return list(set(eliminated))

eliminated_teams = get_eliminated_teams()

# --- 4. PLAYER DATA ENGINE (LIVE ESPN FEED) ---
@st.cache_data(ttl=60)
def pull_tournament_stats():
    all_player_stats = []
    college_map = {}
    
    tourney_dates = ['20260317', '20260318', '20260319', '20260320', '20260321', '20260322']
    
    for date_str in tourney_dates:
        schedule_url = f"https://site.api.espn.com/apis/site/v2/sports/basketball/mens-college-basketball/scoreboard?dates={date_str}"
        try:
            sched_data = requests.get(schedule_url).json()
            events = sched_data.get('events', [])
            
            for game in events:
                status = game['competitions'][0]['status']['type']['description']
                
                # Only pull stats if the game has started or finished
                if status != "Scheduled":
                    game_id = game['id']
                    summary_url = f"https://site.api.espn.com/apis/site/v2/sports/basketball/mens-college-basketball/summary?event={game_id}"
                    summary_data = requests.get(summary_url).json()
                    
                    if 'boxscore' in summary_data and 'players' in summary_data['boxscore']:
                        for team in summary_data['boxscore']['players']:
                            team_name = team['team']['displayName']
                            
                            # Skip if stats array hasn't populated yet
                            if not team.get('statistics'):
                                continue
                                
                            labels = team['statistics'][0]['labels']
                            
                            # Find exactly where the stats are in the array
                            pts_idx = labels.index('PTS') if 'PTS' in labels else -1
                            reb_idx = labels.index('REB') if 'REB' in labels else -1
                            ast_idx = labels.index('AST') if 'AST' in labels else -1
                            
                            for athlete in team['statistics'][0]['athletes']:
                                name = athlete['athlete']['displayName']
                                college_map[name] = team_name # Memorize the college!
                                
                                stats = athlete.get('stats')
                                if stats and pts_idx != -1:
                                    try:
                                        pts = int(stats[pts_idx])
                                        reb = int(stats[reb_idx])
                                        ast = int(stats[ast_idx])
                                    except ValueError:
                                        pts, reb, ast = 0, 0, 0
                                        
                                    all_player_stats.append({
                                        'athlete_display_name': name,
                                        'team_short_display_name': team_name,
                                        'points': pts,
                                        'rebounds': reb,
                                        'assists': ast,
                                        'fantasy_pts': pts + reb + ast,
                                        'game_id': game_id
                                    })
        except Exception as e:
            continue # If a day fails, just keep going
            
    # Convert our collected data into a Pandas DataFrame
    if all_player_stats:
        df = pd.DataFrame(all_player_stats)
    else:
        df = pd.DataFrame(columns=['athlete_display_name', 'team_short_display_name', 'points', 'rebounds', 'assists', 'fantasy_pts', 'game_id'])
        
    return df, college_map

# Unpack both variables from the function
live_data, college_map = pull_tournament_stats()

# --- 5. PROCESSING & LEADERBOARD ---
if player_to_owner:
    roster_base = pd.DataFrame(list(player_to_owner.items()), columns=['Player', 'Fantasy Owner'])
    
    # Assign colleges based on ESPN live data
    if college_map:
        roster_base['College'] = roster_base['Player'].map(college_map).fillna('TBD (Awaiting Tip-off)')
    else:
        roster_base['College'] = 'TBD (Awaiting Tip-off)'
    
    if not live_data.empty:
        drafted_df = live_data[live_data['athlete_display_name'].isin(player_to_owner.keys())].copy()
        
        if not drafted_df.empty:
            player_stats = drafted_df.groupby('athlete_display_name').agg(
                Games_Played=('game_id', 'nunique'),
                Total_Pts=('points', 'sum'),
                Total_Reb=('rebounds', 'sum'),
                Total_Ast=('assists', 'sum'),
                Tourney_Score=('fantasy_pts', 'sum')
            ).reset_index()
            player_stats = player_stats.rename(columns={'athlete_display_name': 'Player'})
        else:
            player_stats = pd.DataFrame(columns=['Player', 'Games_Played', 'Total_Pts', 'Total_Reb', 'Total_Ast', 'Tourney_Score'])
    else:
        player_stats = pd.DataFrame(columns=['Player', 'Games_Played', 'Total_Pts', 'Total_Reb', 'Total_Ast', 'Tourney_Score'])

    full_player_totals = pd.merge(roster_base, player_stats, on='Player', how='left')
    
    full_player_totals.fillna({
        'Games_Played': 0,
        'Total_Pts': 0,
        'Total_Reb': 0,
        'Total_Ast': 0,
        'Tourney_Score': 0
    }, inplace=True)

    stat_columns = ['Games_Played', 'Total_Pts', 'Total_Reb', 'Total_Ast', 'Tourney_Score']
    full_player_totals[stat_columns] = full_player_totals[stat_columns].astype(int)

    # Apply elimination tags
    full_player_totals['Status'] = full_player_totals['College'].apply(
        lambda x: "❌ Eliminated" if x in eliminated_teams else "✅ Active"
    )

    leaderboard = full_player_totals.groupby('Fantasy Owner')['Tourney_Score'].sum().reset_index()
    leaderboard = leaderboard.sort_values(by='Tourney_Score', ascending=False).reset_index(drop=True)
    leaderboard.index += 1 
    
    # --- 6. DRAW THE WEB PAGE ---
    st.header("👑 Overall Leaderboard")
    st.dataframe(
        leaderboard,
        width='stretch', 
        hide_index=False
    )
            
    st.divider()
    
    st.header("📊 Fantasy Team Rosters")
    for owner in leaderboard['Fantasy Owner']:
        with st.expander(f"View roster for {owner}"):
            
            team_slice = full_player_totals[full_player_totals['Fantasy Owner'] == owner].copy()
            team_slice = team_slice.sort_values(by=['Status', 'Tourney_Score'], ascending=[False, False])
            
            display_slice = team_slice.drop(columns=['Fantasy Owner'])
            
            def highlight_eliminated(row):
                return ['color: #ff4b4b;' if (col == 'Player' and row['Status'] == '❌ Eliminated') else '' for col in row.index]
            
            styled_slice = display_slice.style.apply(highlight_eliminated, axis=1)
            
            st.dataframe(styled_slice, width='stretch', height=480, hide_index=True) 

else:
    st.warning("Please create and save your 'rosters.csv' file to load the teams.")