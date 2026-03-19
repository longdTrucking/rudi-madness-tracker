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
        return pd.DataFrame()
        
    try:
        df = pd.read_csv("rosters.csv")
        if 'Fantasy Team' in df.columns:
            df = df.rename(columns={'Fantasy Team': 'Fantasy Owner'})
        # Strip whitespace just to be safe
        df['Player'] = df['Player'].astype(str).str.strip()
        return df
    except Exception as e:
        st.error(f"Failed to read 'rosters.csv': {e}")
        return pd.DataFrame()

roster_base = load_rosters()

# --- 3. THE AUTOMATED COLLEGE LOOKUP (RUNS ONCE EVERY 24 HOURS) ---
@st.cache_data(ttl=86400) 
def build_college_dictionary():
    try:
        import sportsdataverse.mbb as mbb
        # Pull the regular season database (it has everyone in it!)
        df = mbb.load_mbb_player_boxscore(seasons=[2026], return_as_pandas=True)
        
        # Keep only the columns we need and drop all the duplicate games
        mapping_df = df[['athlete_display_name', 'team_short_display_name']].drop_duplicates(subset=['athlete_display_name'])
        
        # Convert it into a lightning-fast Python dictionary
        college_dict = dict(zip(mapping_df.athlete_display_name, mapping_df.team_short_display_name))
        return college_dict
    except Exception as e:
        print(f"Failed to build college dictionary: {e}")
        return {}

college_map = build_college_dictionary()

# Apply the automated colleges to your CSV roster!
if not roster_base.empty:
    roster_base['College'] = roster_base['Player'].map(college_map).fillna('Unknown College')

# --- 4. THE AUTO-ELIMINATION ENGINE (LIVE ESPN FEED) ---
@st.cache_data(ttl=120)
def get_eliminated_teams():
    eliminated = []
    tourney_dates = [
        '20260319', '20260320', '20260321', '20260322', 
        '20260326', '20260327', '20260328', '20260329', 
        '20260404', '20260406'
    ]
    
    for date_str in tourney_dates:
        url = f"https://site.api.espn.com/apis/site/v2/sports/basketball/mens-college-basketball/scoreboard?dates={date_str}"
        try:
            data = requests.get(url).json()
            for event in data.get('events', []):
                comp = event['competitions'][0]
                if comp['status']['type']['completed']: 
                    for team in comp['competitors']:
                        if team.get('winner') == False:
                            eliminated.append(team['team']['displayName'])
                            eliminated.append(team['team']['shortDisplayName']) # Catch both name formats
        except:
            pass
            
    return list(set(eliminated))

eliminated_teams = get_eliminated_teams()

# --- 5. PLAYER DATA ENGINE (LIVE ESPN FEED) ---
@st.cache_data(ttl=60)
def pull_tournament_stats():
    all_player_stats = []
    tourney_dates = [
        '20260319', '20260320', '20260321', '20260322', 
        '20260326', '20260327', '20260328', '20260329', 
        '20260404', '20260406'
    ]
    
    for date_str in tourney_dates:
        schedule_url = f"https://site.api.espn.com/apis/site/v2/sports/basketball/mens-college-basketball/scoreboard?dates={date_str}"
        try:
            sched_data = requests.get(schedule_url).json()
            events = sched_data.get('events', [])
            
            for game in events:
                status = game['competitions'][0]['status']['type']['description']
                
                if status != "Scheduled":
                    game_id = game['id']
                    summary_url = f"https://site.api.espn.com/apis/site/v2/sports/basketball/mens-college-basketball/summary?event={game_id}"
                    
                    try:
                        summary_data = requests.get(summary_url).json()
                        if 'boxscore' in summary_data and 'players' in summary_data['boxscore']:
                            for team in summary_data['boxscore']['players']:
                                if not team.get('statistics'):
                                    continue
                                    
                                labels = team['statistics'][0]['labels']
                                pts_idx = labels.index('PTS') if 'PTS' in labels else -1
                                reb_idx = labels.index('REB') if 'REB' in labels else -1
                                ast_idx = labels.index('AST') if 'AST' in labels else -1
                                
                                for athlete in team['statistics'][0]['athletes']:
                                    name = athlete['athlete']['displayName']
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
                                            'points': pts,
                                            'rebounds': reb,
                                            'assists': ast,
                                            'fantasy_pts': pts + reb + ast,
                                            'game_id': game_id
                                        })
                    except:
                        continue
        except:
            continue
            
    if all_player_stats:
        return pd.DataFrame(all_player_stats)
    else:
        return pd.DataFrame(columns=['athlete_display_name', 'points', 'rebounds', 'assists', 'fantasy_pts', 'game_id'])

live_data = pull_tournament_stats()

# --- 6. PROCESSING & LEADERBOARD ---
if not roster_base.empty:
    if not live_data.empty:
        drafted_df = live_data[live_data['athlete_display_name'].isin(roster_base['Player'])].copy()
        
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

    # Check eliminations against the automatically assigned college!
    full_player_totals['Status'] = full_player_totals['College'].apply(
        lambda x: "❌ Eliminated" if x in eliminated_teams else "✅ Active"
    )

    leaderboard = full_player_totals.groupby('Fantasy Owner')['Tourney_Score'].sum().reset_index()
    leaderboard = leaderboard.sort_values(by='Tourney_Score', ascending=False).reset_index(drop=True)
    leaderboard.index += 1 
    
    # --- 7. DRAW THE WEB PAGE ---
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
    st.warning("Please create your 'rosters.csv' file with Player and Fantasy Team columns.")
